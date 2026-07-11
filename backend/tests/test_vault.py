"""Encrypted secrets vault (plan 20, part 5).

Covers Fernet encryption at rest, masked list vs the separate reveal path, rotation, expiry,
``resolve_env_dict`` injection, workspace scoping, and the admin-gated HTTP surface.
"""
import time

import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.vault import VaultMixin
from devicekit.mixins.workspaces import WorkspacesMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.services.gate import authorize
from devicekit.models.secret_vault import Secret
from devicekit.db import session_scope
from devicekit.notifications import crypto
from devicekit.routes import vault as vault_routes


class _VaultClient(VaultMixin, WorkspacesMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _VaultClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- encryption at rest
def test_secret_encrypted_at_rest(client):
    v = client.create_vault("Fleet creds")
    client.set_secret(v["id"], "WIFI_PASSWORD", "s3cr3t-wifi")
    # Stored ciphertext is enc:-prefixed and is NOT the plaintext.
    with session_scope() as s:
        row = s.query(Secret).filter(Secret.vault_id == v["id"]).first()
        assert crypto.is_encrypted(row.value)
        assert "s3cr3t-wifi" not in row.value
    # Reveal round-trips.
    revealed = client.reveal_secret(v["id"], "WIFI_PASSWORD")
    assert revealed["value"] == "s3cr3t-wifi"


def test_list_is_masked(client):
    v = client.create_vault("V")
    client.set_secret(v["id"], "API_TOKEN", "abc123")
    listed = client.list_secrets(v["id"])
    assert len(listed) == 1
    assert listed[0]["value"] == "••••••••" and listed[0]["has_value"] is True
    assert "abc123" not in str(listed[0])


def test_rotation_and_delete(client):
    v = client.create_vault("V")
    client.set_secret(v["id"], "K", "v1")
    client.set_secret(v["id"], "K", "v2")   # upsert = rotate
    assert client.reveal_secret(v["id"], "K")["value"] == "v2"
    assert len(client.list_secrets(v["id"])) == 1   # still one row
    client.delete_secret(v["id"], "K")
    with pytest.raises(ValueError):
        client.reveal_secret(v["id"], "K")


def test_resolve_env_dict_skips_expired(client):
    v = client.create_vault("V")
    client.set_secret(v["id"], "LIVE", "yes")
    client.set_secret(v["id"], "DEAD", "no", expires_at=time.time() - 1)
    env = client.resolve_env_dict(v["id"])
    assert env == {"LIVE": "yes"}
    assert client.resolve_env_dict(v["id"], include_expired=True) == {"LIVE": "yes", "DEAD": "no"}


def test_set_requires_value(client):
    v = client.create_vault("V")
    with pytest.raises(ValueError):
        client.set_secret(v["id"], "K", "")
    with pytest.raises(ValueError):
        client.set_secret("nope", "K", "v")   # vault not found


def test_vault_workspace_scoping(client):
    ws = client.create_workspace("Team", created_by=None)
    client.create_vault("global-v")
    client.create_vault("ws-v", workspace_id=ws["id"])
    assert len(client.list_vaults()) == 2
    scoped = client.list_vaults(workspace_id=ws["id"])
    assert [v["name"] for v in scoped] == ["ws-v"]


# --------------------------------------------------------------- HTTP (admin-gated)
def test_http_admin_gated_and_reveal_path(client):
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(vault_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc = app.test_client()
    # Solo mode → admin. Create vault + secret.
    v = tc.post("/vault/vaults", json={"name": "Prod"}).get_json()["vault"]
    r = tc.post(f"/vault/vaults/{v['id']}/secrets",
                json={"key": "DB_PASSWORD", "value": "hunter2"})
    assert r.status_code == 201
    # List is masked.
    listed = tc.get(f"/vault/vaults/{v['id']}/secrets").get_json()["secrets"]
    assert listed[0]["value"] == "••••••••"
    # Reveal path returns plaintext.
    revealed = tc.post(f"/vault/vaults/{v['id']}/secrets/DB_PASSWORD/reveal").get_json()["secret"]
    assert revealed["value"] == "hunter2"

    # A viewer principal is forbidden.
    client.create_user("v", "pw123456", role="viewer")
    tok = client.create_session(client.list_users()[0]["id"])
    h = {"X-Session-Token": tok}
    assert tc.get("/vault/vaults", headers=h).status_code == 403
    assert tc.post("/vault/vaults", headers=h, json={"name": "x"}).status_code == 403
