"""Hashed, scoped API keys (plan 20, part 2).

Covers generation/hashing/scope validation, the CRUD + rotate/revoke lifecycle, principal
resolution with wildcard scope matching, and the HTTP gate honoring key scopes.
"""
import time

import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.api_keys import ApiKeysMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.services.gate import authorize
from devicekit.services import api_keys as svc
from devicekit.routes import api_keys as api_keys_routes


class _KeyClient(ApiKeysMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _KeyClient()
    c.init_identity()
    return c


@pytest.fixture
def app_client(client):
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(api_keys_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    @app.route("/automations", methods=["POST"])
    def _mk():
        return jsonify({"ok": True})

    @app.route("/devices/<dev>/reboot", methods=["POST"])
    def _reboot(dev):
        return jsonify({"ok": True})

    return app.test_client(), client


# --------------------------------------------------------------- primitives
def test_key_format_and_hash():
    raw, prefix, key_hash = svc.generate_key()
    assert raw.startswith("dk_")
    assert prefix == raw[:11] and len(key_hash) == 64
    assert svc.hash_key(raw) == key_hash
    assert svc.looks_like_key(raw) and not svc.looks_like_key("sk_x")


def test_scope_validation():
    assert svc.validate_scopes(["devices:*", "devices:*", "automations:read"]) == \
        ["devices:*", "automations:read"]
    assert svc.validate_scopes(["*"]) == ["*"]
    with pytest.raises(ValueError):
        svc.validate_scopes(["devices:delete"])
    with pytest.raises(ValueError):
        svc.validate_scopes("devices:read")  # not a list


# --------------------------------------------------------------- lifecycle
def test_create_returns_raw_key_once(client):
    created = client.create_api_key("ci", scopes=["automations:write"])
    assert created["key"].startswith("dk_")
    assert created["scopes"] == ["automations:write"] and created["status"] == "active"
    # The raw key is never in the stored/listed representation.
    listed = client.list_api_keys()
    assert len(listed) == 1 and "key" not in listed[0]
    assert listed[0]["prefix"] == created["prefix"]


def test_create_requires_name_and_scopes(client):
    with pytest.raises(ValueError):
        client.create_api_key("", scopes=["*"])
    with pytest.raises(ValueError):
        client.create_api_key("x", scopes=[])


def test_revoke_and_rotate(client):
    created = client.create_api_key("k", scopes=["*"])
    revoked = client.revoke_api_key(created["id"])
    assert revoked["status"] == "revoked"
    # A revoked key no longer authenticates.
    assert client.resolve_api_key_principal(created["key"]) is None

    fresh = client.create_api_key("k2", scopes=["devices:read"])
    rotated = client.rotate_api_key(fresh["id"])
    assert rotated["key"] != fresh["key"] and rotated["scopes"] == ["devices:read"]
    assert client.get_api_key(fresh["id"])["status"] == "revoked"
    assert client.resolve_api_key_principal(rotated["key"]) is not None


def test_expired_key_rejected(client):
    created = client.create_api_key("temp", scopes=["*"],
                                    expires_at=time.time() - 1)
    assert client.get_api_key(created["id"])["status"] == "expired"
    assert client.resolve_api_key_principal(created["key"]) is None


# --------------------------------------------------------------- principal + scopes
def test_principal_wildcard_scopes(client):
    created = client.create_api_key("wild", scopes=["devices:*", "automations:read"])
    p = client.resolve_api_key_principal(created["key"])
    assert p.kind == "apikey" and p.api_key_id == created["id"]
    assert p.can("devices", "read") and p.can("devices", "write")   # devices:* ⇒ both
    assert p.can("automations", "read") and not p.can("automations", "write")
    assert not p.can("settings", "write")


def test_star_scope_is_full(client):
    created = client.create_api_key("root", scopes=["*"])
    p = client.resolve_api_key_principal(created["key"])
    assert p.can("settings", "write") and p.can("agents", "write")
    assert not p.is_admin  # a key is not an admin *principal* (can't manage users/keys)


def test_last_used_tracked(client):
    created = client.create_api_key("track", scopes=["*"])
    assert client.get_api_key(created["id"])["last_used_at"] is None

    class Req:
        remote_addr = "9.9.9.9"
    client.resolve_api_key_principal(created["key"], Req())
    assert client.get_api_key(created["id"])["last_used_at"] is not None
    assert client.get_api_key(created["id"])["last_used_ip"] == "9.9.9.9"


# --------------------------------------------------------------- HTTP gate
def test_gate_honors_key_scopes(app_client):
    tc, c = app_client
    key = c.create_api_key("scoped", scopes=["automations:write"])["key"]
    h = {"X-API-Key": key}
    assert tc.post("/automations", headers=h).status_code == 200
    assert tc.post("/devices/d1/reboot", headers=h).status_code == 403


def test_key_management_admin_only(app_client):
    tc, c = app_client
    # A scoped key is authenticated but not an admin principal → cannot list keys.
    key = c.create_api_key("scoped", scopes=["*"])["key"]
    assert tc.get("/api-keys", headers={"X-API-Key": key}).status_code == 403
    # Solo mode (no users, no key configured) → admin principal → allowed.
    c2 = _KeyClient()
    c2.init_identity()
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(api_keys_routes.make_blueprint(c2, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(c2, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc2 = app.test_client()
    assert tc2.get("/api-keys").status_code == 200
    r = tc2.post("/api-keys", json={"name": "made-in-ui", "scopes": ["devices:read"]})
    assert r.status_code == 201 and r.get_json()["api_key"]["key"].startswith("dk_")
