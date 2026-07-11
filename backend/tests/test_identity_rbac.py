"""Identity, roles & the auth gate (plan 20, part 1).

Covers the permission matrix (role templates, narrow-only overrides, write⇒read), the identity
mixin (users, sessions, last-admin guards, solo-mode fallback), and the HTTP gate end-to-end
through a Flask test client wired to the *real* ``authorize`` decision function.
"""
import pytest
from flask import Flask, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.services.gate import authorize
from devicekit.services.permissions import (
    resolve_permissions, validate_overrides, PermissionError,
)
from devicekit.routes import auth as auth_routes


class _IdentityClient(IdentityMixin, AuthMixin):
    """Minimal composite: identity + token validation, no devices/DB-heavy mixins."""

    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("DEVICEKIT_ADMIN_PASSWORD", raising=False)
    c = _IdentityClient()
    c.init_identity()
    return c


@pytest.fixture
def app_client(client):
    """A Flask test client whose before_request calls the real ``authorize`` gate."""
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(auth_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, __import__("flask").request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    # Dummy gated write routes standing in for real resource blueprints.
    @app.route("/automations", methods=["POST"])
    def _mk_automation():
        return jsonify({"ok": True})

    @app.route("/devices/<dev>/reboot", methods=["POST"])
    def _reboot(dev):
        return jsonify({"ok": True})

    return app.test_client(), client


# --------------------------------------------------------------------- permission matrix
def test_role_templates():
    admin = resolve_permissions("admin")
    assert all(v["read"] and v["write"] for v in admin.values())
    viewer = resolve_permissions("viewer")
    assert viewer["devices"]["read"] and not viewer["devices"]["write"]
    assert not viewer["commands"]["read"]
    operator = resolve_permissions("operator")
    assert operator["automations"]["write"] and not operator["devices"]["write"]


def test_override_write_implies_read():
    with pytest.raises(PermissionError):
        validate_overrides({"devices": {"read": False, "write": True}}, "operator")


def test_override_rejects_unknown_feature():
    with pytest.raises(PermissionError):
        validate_overrides({"bogus": {"read": True}}, "operator")


def test_override_narrow_only_cannot_elevate():
    # A viewer cannot be granted command write via an override (elevation beyond the role).
    with pytest.raises(PermissionError):
        validate_overrides({"commands": {"read": True, "write": True}}, "viewer")


def test_override_narrows_role():
    out = validate_overrides({"automations": {"read": True, "write": False}}, "operator")
    assert out == {"automations": {"read": True, "write": False}}
    resolved = resolve_permissions("operator", {"automations": {"read": True, "write": False}})
    assert not resolved["automations"]["write"]


# --------------------------------------------------------------------- identity mixin
def test_solo_mode_when_no_users(client):
    class Req:
        headers, args, cookies = {}, {}, {}
    p = client.resolve_principal(Req())
    assert p.kind == "solo" and p.full_access and p.is_admin


def test_first_user_flips_to_login_required(client):
    client.create_user("alice", "pw123456", role="operator")

    class Req:
        headers, args, cookies = {}, {}, {}
    assert client.resolve_principal(Req()) is None


def test_credentials_and_session_roundtrip(client):
    u = client.create_user("bob", "pw123456", role="viewer")
    assert client.verify_credentials("bob", "nope") is None
    assert client.verify_credentials("bob", "pw123456")["role"] == "viewer"

    token = client.create_session(u["id"], ip="1.1.1.1", user_agent="pytest")

    class Req:
        headers = {"X-Session-Token": token}
        args, cookies = {}, {}
    p = client.resolve_principal(Req())
    assert p.kind == "user" and p.username == "bob" and not p.full_access
    assert client.delete_session(token) is True
    assert client.resolve_principal(Req()) is None


def test_duplicate_username_rejected(client):
    client.create_user("dup", "pw123456")
    with pytest.raises(ValueError):
        client.create_user("dup", "otherpw12")


def test_last_admin_guards(client):
    admin = client.create_user("root", "pw123456", role="admin")
    with pytest.raises(ValueError):
        client.update_user(admin["id"], role="viewer")
    with pytest.raises(ValueError):
        client.update_user(admin["id"], is_active=False)
    with pytest.raises(ValueError):
        client.delete_user(admin["id"])
    # A second admin lifts the guard.
    client.create_user("root2", "pw123456", role="admin")
    assert client.update_user(admin["id"], role="operator")["role"] == "operator"


def test_legacy_api_key_principal():
    c = _IdentityClient(api_key="secret-key")
    c.init_identity()

    class Req:
        headers = {"X-API-Key": "secret-key"}
        args, cookies = {}, {}
    p = c.resolve_principal(Req())
    assert p.kind == "legacy" and p.full_access

    class BadReq:
        headers = {"X-API-Key": "wrong"}
        args, cookies = {}, {}
    assert c.resolve_principal(BadReq()) is None


# --------------------------------------------------------------------- HTTP gate
def test_gate_solo_allows_writes(app_client):
    tc, _ = app_client
    assert tc.post("/automations").status_code == 200  # solo full access


def test_gate_login_and_role_enforcement(app_client):
    tc, c = app_client
    c.create_user("admin", "pw123456", role="admin")
    c.create_user("op", "pw123456", role="operator")
    c.create_user("view", "pw123456", role="viewer")

    # Unauthenticated write is now rejected.
    assert tc.post("/automations").status_code == 401

    def login(username):
        r = tc.post("/auth/login", json={"username": username, "password": "pw123456"})
        assert r.status_code == 200
        return {"X-Session-Token": r.get_json()["token"]}

    # Operator: can write automations, cannot reboot a device.
    op = login("op")
    assert tc.post("/automations", headers=op).status_code == 200
    assert tc.post("/devices/d1/reboot", headers=op).status_code == 403

    # Viewer: cannot write automations.
    view = login("view")
    assert tc.post("/automations", headers=view).status_code == 403

    # Admin: everything.
    admin = login("admin")
    assert tc.post("/automations", headers=admin).status_code == 200
    assert tc.post("/devices/d1/reboot", headers=admin).status_code == 200


def test_users_crud_admin_only(app_client):
    tc, c = app_client
    c.create_user("admin", "pw123456", role="admin")
    c.create_user("view", "pw123456", role="viewer")

    def login(username):
        r = tc.post("/auth/login", json={"username": username, "password": "pw123456"})
        return {"X-Session-Token": r.get_json()["token"]}

    admin, view = login("admin"), login("view")
    # Viewer can't read the roster.
    assert tc.get("/users", headers=view).status_code == 403
    # Admin can, and can create a user.
    assert tc.get("/users", headers=admin).status_code == 200
    r = tc.post("/users", headers=admin,
                json={"username": "new", "password": "pw123456", "role": "operator"})
    assert r.status_code == 201 and r.get_json()["user"]["role"] == "operator"


def test_bad_login_401(app_client):
    tc, c = app_client
    c.create_user("admin", "pw123456", role="admin")
    assert tc.post("/auth/login", json={"username": "admin", "password": "x"}).status_code == 401


def test_session_endpoint_reports_state(app_client):
    tc, c = app_client
    # Solo mode: authenticated, no login required.
    body = tc.get("/auth/session").get_json()
    assert body["authenticated"] and not body["login_required"] and not body["has_users"]

    c.create_user("admin", "pw123456", role="admin")
    body = tc.get("/auth/session").get_json()
    assert not body["authenticated"] and body["login_required"] and body["has_users"]
