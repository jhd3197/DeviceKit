"""The public ``/api/v1`` surface (plan 21, part 1).

Covers the version-strip + scope-table primitives, the ``/api/v1`` discovery/catalog
endpoints, the mirrored blueprints (same handlers bare and under ``/api/v1``), and the
central gate + ``require_scope`` decorator enforcing ``dk_``-key scopes uniformly on
reads *and* writes while session/solo principals pass through.
"""
import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.api_keys import ApiKeysMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.routes import api_v1, automations, device_control, devices, health
from devicekit.services.api_keys import validate_scopes
from devicekit.services.gate import authorize
from devicekit.services.scopes import (
    available_scopes,
    require_scope,
    scope_allows,
    scope_for_request,
    strip_version,
)


class _V1Host(ApiKeysMixin, IdentityMixin, AuthMixin):
    """Mixin composite with plain stubs for everything the mounted handlers call."""

    def __init__(self):
        self.configure_auth("", [])
        self._has_users_flag = None
        self._agent_device_states = {}   # routes/devices.py agent-merge loop

    # --- routes/devices.py ---------------------------------------------------
    def get_connected_devices(self):
        return []                        # nothing new → no onboarding loop

    def get_devices(self):
        return [{"serial": "x", "device_id": "x", "model": "Pixel Test",
                 "manufacturer": "Test"}]

    def find_agent_device(self, device_id):
        return None

    # --- routes/device_control.py ---------------------------------------------
    def click(self, x, y, device_id):
        return True

    def log_activity(self, *args, **kwargs):
        return None

    # --- routes/automations.py -------------------------------------------------
    def list_automations(self, workspace_id=None):
        return []

    def execute_automation(self, automation_id, device_id, self_heal=False):
        return {"id": "run-1", "automation_id": automation_id,
                "device_id": device_id, "status": "queued"}


def _make_app(host):
    """A small real app: gate wired in before_request, blueprints mounted bare AND
    mirrored under /api/v1 exactly like ``register_all`` does."""
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[],
                      storage_uri="memory://")
    for module in (api_v1, health, devices, device_control, automations):
        app.register_blueprint(module.make_blueprint(host, limiter))
        if module is not api_v1:
            bp = module.make_blueprint(host, limiter)
            app.register_blueprint(bp, url_prefix="/api/v1", name=f"v1_{bp.name}")

    @app.before_request
    def _gate():
        principal, error = authorize(host, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    # Deliberately on a path no feature prefix maps to, so the central gate never
    # requires a scope here — only the decorator does (the direct decorator test).
    @app.route("/sandbox/decorated")
    @require_scope("metrics:read")
    def _decorated():
        return jsonify({"ok": True})

    return app


@pytest.fixture
def host(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    h = _V1Host()
    h.init_identity()
    return h


@pytest.fixture
def app_client(host):
    return _make_app(host).test_client(), host


# ------------------------------------------------------------- pure functions
def test_strip_version():
    assert strip_version("/api/v1/devices") == "/devices"
    assert strip_version("/devices") == "/devices"
    assert strip_version("/api/v1") == "/"
    # Only the exact prefix is stripped — /api/v10 is not v1.
    assert strip_version("/api/v10/devices") == "/api/v10/devices"


def test_scope_allows_write_implies_narrower_verbs():
    assert scope_allows(["devices:write"], "devices:command")
    assert scope_allows(["devices:write"], "devices:read")
    # The reverse never holds: command is a carve-out, not a superset.
    assert not scope_allows(["devices:command"], "devices:write")
    assert not scope_allows(["devices:command"], "devices:read")
    # Wildcards.
    assert scope_allows(["*"], "fleet:admin")
    assert scope_allows(["devices:*"], "devices:command")
    # Cross-feature denial.
    assert not scope_allows(["devices:*"], "automations:read")
    assert not scope_allows(["automations:run"], "devices:command")


def test_scope_for_request_table():
    assert scope_for_request("/devices/x/tap", "POST") == "devices:command"
    assert scope_for_request("/devices", "GET") == "devices:read"
    assert scope_for_request("/automations/a/run", "POST") == "automations:run"
    assert scope_for_request("/fleet/groups/g/bulk/reboot", "POST") == "fleet:admin"
    assert scope_for_request("/extensions/install", "POST") == "extensions:admin"
    # Read-shaped POST: validating an FQL expression mutates nothing.
    assert scope_for_request("/fleet/query/validate", "POST") == "devices:read"
    # Plain feature fallbacks.
    assert scope_for_request("/automations", "POST") == "automations:write"
    # Unmapped paths are auth-only.
    assert scope_for_request("/workspaces", "GET") is None


def test_catalog_has_new_verbs_and_validate_scopes_accepts_them():
    catalog = set(available_scopes())
    assert {"devices:command", "automations:run", "extensions:admin",
            "fleet:admin", "fleet:*", "*", "devices:read", "devices:write"} <= catalog
    assert validate_scopes(["devices:command"]) == ["devices:command"]
    with pytest.raises(ValueError):
        validate_scopes(["bogus:scope"])


# ------------------------------------------------------------------ solo mode
def test_solo_mode_v1_mirror_and_meta(app_client):
    tc, _ = app_client
    bare = tc.get("/devices")
    mirrored = tc.get("/api/v1/devices")
    assert bare.status_code == 200 and mirrored.status_code == 200
    assert mirrored.get_json() == bare.get_json()
    assert mirrored.get_json()["count"] == 1

    disc = tc.get("/api/v1")
    assert disc.status_code == 200
    body = disc.get_json()
    assert body["api_version"] == "v1" and body["scopes_url"] == "/api/v1/scopes"

    cat = tc.get("/api/v1/scopes")
    assert cat.status_code == 200
    body = cat.get_json()
    assert body["count"] == len(body["scopes"]) > 0
    assert {"scope", "description"} <= set(body["scopes"][0])


def test_health_is_public_on_both_mounts(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")   # auth now required everywhere else
    assert tc.get("/health").status_code == 200
    assert tc.get("/api/v1/health").status_code == 200


# ---------------------------------------------------------------- scoped keys
def test_auth_required_once_users_exist(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    r = tc.get("/api/v1/devices")
    assert r.status_code == 401
    assert r.get_json() == {"error": "Authentication required"}


def test_read_key_reads_uniformly_but_cannot_write_or_cross_feature(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    key = host.create_api_key("reader", scopes=["devices:read"])["key"]
    h = {"X-API-Key": key}
    assert tc.get("/api/v1/devices", headers=h).status_code == 200
    assert tc.get("/devices", headers=h).status_code == 200   # same gate on both mounts

    r = tc.get("/api/v1/automations", headers=h)
    assert r.status_code == 403 and "automations:read" in r.get_json()["error"]

    r = tc.post("/api/v1/devices/x/tap", headers=h, json={"x": 1, "y": 2})
    assert r.status_code == 403 and "devices:command" in r.get_json()["error"]


def test_command_key_commands_but_cannot_read(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    key = host.create_api_key("commander", scopes=["devices:command"])["key"]
    h = {"X-API-Key": key}
    r = tc.post("/api/v1/devices/x/tap", headers=h, json={"x": 1, "y": 2})
    assert r.status_code == 200 and r.get_json()["status"] == "ok"
    # command does not imply read.
    r = tc.get("/api/v1/devices", headers=h)
    assert r.status_code == 403 and "devices:read" in r.get_json()["error"]


def test_write_key_implies_command(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    key = host.create_api_key("writer", scopes=["devices:write"])["key"]
    r = tc.post("/api/v1/devices/x/tap", headers={"X-API-Key": key},
                json={"x": 1, "y": 2})
    assert r.status_code == 200


def test_run_key_runs_automations_but_cannot_list(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    key = host.create_api_key("runner", scopes=["automations:run"])["key"]
    h = {"X-API-Key": key}
    r = tc.post("/api/v1/automations/a/run", headers=h, json={"device_id": "x"})
    assert r.status_code == 201 and r.get_json()["status"] == "queued"
    r = tc.get("/api/v1/automations", headers=h)
    assert r.status_code == 403 and "automations:read" in r.get_json()["error"]


def test_star_key_full_access(app_client):
    tc, host = app_client
    host.create_user("admin", "pw", role="admin")
    h = {"X-API-Key": host.create_api_key("root", scopes=["*"])["key"]}
    assert tc.get("/api/v1/devices", headers=h).status_code == 200
    assert tc.get("/api/v1/automations", headers=h).status_code == 200
    assert tc.post("/api/v1/devices/x/tap", headers=h,
                   json={"x": 1, "y": 2}).status_code == 200
    assert tc.post("/api/v1/automations/a/run", headers=h,
                   json={"device_id": "x"}).status_code == 201


# ------------------------------------------------------------------- sessions
def test_session_user_passes_without_scopes(app_client):
    tc, host = app_client
    user = host.create_user("admin", "pw", role="admin")
    token = host.create_session(user["id"])
    h = {"X-Session-Token": token}
    # No scope list on a user principal → the scope gate never applies.
    assert tc.get("/api/v1/devices", headers=h).status_code == 200
    assert tc.post("/api/v1/devices/x/tap", headers=h,
                   json={"x": 1, "y": 2}).status_code == 200


# ------------------------------------------------------- require_scope decorator
def test_require_scope_decorator_direct(app_client):
    tc, host = app_client
    # Solo (no users yet): pass-through.
    assert tc.get("/sandbox/decorated").status_code == 200

    user = host.create_user("admin", "pw", role="admin")
    # The central gate does not scope this unmapped path — only the decorator does.
    bad = host.create_api_key("no-metrics", scopes=["devices:read"])["key"]
    r = tc.get("/sandbox/decorated", headers={"X-API-Key": bad})
    assert r.status_code == 403
    assert r.get_json() == {"error": "Missing required scope: metrics:read"}

    good = host.create_api_key("metrics", scopes=["metrics:read"])["key"]
    assert tc.get("/sandbox/decorated",
                  headers={"X-API-Key": good}).status_code == 200

    # Session principals pass straight through.
    token = host.create_session(user["id"])
    assert tc.get("/sandbox/decorated",
                  headers={"X-Session-Token": token}).status_code == 200
