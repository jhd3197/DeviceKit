"""The gated actions surface — ``GET /actions`` + ``POST /actions/invoke`` (plan 21, part 3).

Drives the real blueprint through the real auth gate (``authorize`` in before_request,
mounted bare and mirrored under ``/api/v1`` exactly like ``register_all``) against a mixin
composite whose device layer is stubbed. Writes route through the genuine plan-13
confirmation gate: the invoke request blocks on a background thread while the test plays
the human — polling ``list_pending_actions`` and releasing via ``confirm_action`` — so the
pending/approve/deny/timeout dance is exercised end to end.

Key semantics under test: route-level scope classes (reads ``devices:read``, writes
``devices:command``, ``run_automation`` ``automations:run``), the forced gate for every
``dk_`` key without the *exact* ``mcp:autonomous`` opt-in (wildcards deliberately don't
count), and the auto-approve path when the opt-in meets an autonomous-mode device.
"""
import threading
import time

import pytest
from flask import Flask, g, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.agent_gate import AgentGateMixin
from devicekit.mixins.api_keys import ApiKeysMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.routes import actions
from devicekit.services.gate import authorize

DEV = "ACTDEV"


class _ActionsHost(AgentGateMixin, ApiKeysMixin, IdentityMixin, AuthMixin):
    """Composite with real gate/identity/key layers and stubbed device hardware."""

    def __init__(self):
        self.configure_auth("", [])          # auth disabled → solo until a user exists
        self._has_users_flag = None
        self._agent_conversations = {}       # set_agent_mode's observe-crossing rebuild
        self._ensure_gate()                  # instance-local lock + mode/pending dicts
        self.broadcasts = []                 # SSE collector (pending_action / resolved)
        self.clicks = []                     # tap tool's hardware call
        self.automation_runs = []
        self._gate_timeout = 3               # short so a wedged gate can't stall the suite

    # --- AgentGateMixin collaborators ------------------------------------
    def get_profile_by_device(self, device_id):
        return None

    def ai_default_agent_mode(self):
        return "supervised"

    def ai_gate_timeout_seconds(self):
        return self._gate_timeout

    def broadcast(self, event, data):
        self.broadcasts.append((event, data))

    # --- device layer used by the curated tools --------------------------
    def click(self, x, y, device_id):
        self.clicks.append((x, y, device_id))

    def get_device_battery(self, device=None):
        return {"level": 88, "status": "charging"}

    def execute_automation(self, automation_id, device_id, self_heal=False):
        self.automation_runs.append((automation_id, device_id))
        return {"id": "run-1", "automation_id": automation_id,
                "device_id": device_id, "status": "queued"}


def _make_app(host):
    """Actions blueprint bare + mirrored under /api/v1 with the central gate, like
    ``register_all`` + ``api_app`` wire it."""
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[],
                      storage_uri="memory://")
    app.register_blueprint(actions.make_blueprint(host, limiter))
    bp = actions.make_blueprint(host, limiter)
    app.register_blueprint(bp, url_prefix="/api/v1", name=f"v1_{bp.name}")

    @app.before_request
    def _gate():
        principal, error = authorize(host, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    return app


@pytest.fixture
def host(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    h = _ActionsHost()
    h.init_identity()
    return h


@pytest.fixture
def app(host):
    return _make_app(host)


@pytest.fixture
def tc(app):
    return app.test_client()


def _key(host, scopes, name="k"):
    """Mint a dk_ key; creates the admin that flips the instance out of solo mode."""
    if not host.has_users():
        host.create_user("admin", "pw", role="admin")
    return {"X-API-Key": host.create_api_key(name, scopes=scopes)["key"]}


def _invoke_async(app, payload, headers=None, path="/api/v1/actions/invoke"):
    """POST invoke on a background thread (the request blocks on the gate Event)."""
    box = {}

    def run():
        with app.test_client() as c:
            r = c.post(path, json=payload, headers=headers or {})
            box["status_code"] = r.status_code
            box["json"] = r.get_json()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, box


def _wait_pending(host, device, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = host.list_pending_actions(device)
        if pending:
            return pending
        time.sleep(0.02)
    raise AssertionError(f"no pending action appeared for {device}")


def _finish(t, box):
    t.join(timeout=6)
    assert not t.is_alive(), "invoke request never returned"
    assert box["status_code"] == 200
    return box["json"]


# ----------------------------------------------------------------- GET /actions
def test_actions_list_catalog_excludes_extensions(host, tc):
    # An active extension tool must NOT leak into the curated catalog.
    host._ext_ai_tools = {"demo": [("wipe", lambda: "gone", "Wipe it", True)]}
    host.get_extension = lambda slug: {"status": "active"}

    r = tc.get("/api/v1/actions", headers=_key(host, ["devices:read"]))
    assert r.status_code == 200
    body = r.get_json()
    assert body["count"] == len(body["actions"])
    by_name = {a["name"]: a for a in body["actions"]}

    tap = by_name["tap"]
    assert tap["is_write"] is True and tap["scope"] == "devices:command"
    battery = by_name["get_battery"]
    assert battery["is_write"] is False and battery["scope"] == "devices:read"
    run = by_name["run_automation"]
    assert run["is_write"] is True and run["scope"] == "automations:run"
    assert "automation_id" in run["parameters"]["properties"]

    assert all(a["category"] != "extension" for a in body["actions"])
    assert not any(n.startswith("demo__") for n in by_name)


def test_actions_list_requires_devices_read(host, tc):
    r = tc.get("/actions", headers=_key(host, ["automations:*"]))
    assert r.status_code == 403
    assert "devices:read" in r.get_json()["error"]


# ----------------------------------------------------------- invoke validation
def test_invoke_validation_errors(tc):
    # Solo mode (no users) → the request layer alone is under test.
    assert tc.post("/api/v1/actions/invoke",
                   json={"action": "tap"}).status_code == 400
    assert tc.post("/api/v1/actions/invoke",
                   json={"device_id": DEV}).status_code == 400
    r = tc.post("/api/v1/actions/invoke",
                json={"device_id": DEV, "action": "tap", "args": [1, 2]})
    assert r.status_code == 400 and "args" in r.get_json()["error"]
    r = tc.post("/actions/invoke",
                json={"device_id": DEV, "action": "warp_drive", "args": {}})
    assert r.status_code == 404 and "warp_drive" in r.get_json()["error"]
    r = tc.post("/actions/invoke",
                json={"device_id": DEV, "action": "run_automation", "args": {}})
    assert r.status_code == 400 and "automation_id" in r.get_json()["error"]


# ---------------------------------------------------------------- scope gates
def test_read_key_cannot_invoke_write(host, tc):
    r = tc.post("/api/v1/actions/invoke", headers=_key(host, ["devices:read"]),
                json={"device_id": DEV, "action": "tap", "args": {"x": 1, "y": 2}})
    assert r.status_code == 403
    assert "devices:command" in r.get_json()["error"]
    assert host.clicks == []


def test_command_key_cannot_invoke_read(host, tc):
    r = tc.post("/actions/invoke", headers=_key(host, ["devices:command"]),
                json={"device_id": DEV, "action": "get_battery", "args": {}})
    assert r.status_code == 403
    assert "devices:read" in r.get_json()["error"]


# --------------------------------------------------- supervised gate (dk_ key)
def test_supervised_key_tap_blocks_until_approved(host, app):
    h = _key(host, ["devices:command"])
    t, box = _invoke_async(app, {"device_id": DEV, "action": "tap",
                                 "args": {"x": 10, "y": 20}}, headers=h)
    pending = _wait_pending(host, DEV)
    assert len(pending) == 1
    assert pending[0]["tool"] == "tap"
    assert pending[0]["source"] == "api"
    assert host.clicks == [], "tap ran before approval"

    host.confirm_action(pending[0]["id"], True, approver="tester", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "ok" and body["action"] == "tap"
    assert "Tapped" in body["result"]
    assert host.clicks == [(10, 20, DEV)]
    assert host.list_pending_actions(DEV) == []


def test_supervised_key_tap_denied(host, app):
    h = _key(host, ["devices:command"])
    t, box = _invoke_async(app, {"device_id": DEV, "action": "tap",
                                 "args": {"x": 3, "y": 4}}, headers=h)
    pending = _wait_pending(host, DEV)
    host.confirm_action(pending[0]["id"], False, approver="tester", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "denied"
    assert body["result"].startswith("DENIED")
    assert host.clicks == [], "denied tap must not run"


def test_run_automation_gated_then_approved(host, app):
    h = _key(host, ["automations:run"])
    t, box = _invoke_async(app, {"device_id": DEV, "action": "run_automation",
                                 "args": {"automation_id": "a1"}}, headers=h)
    pending = _wait_pending(host, DEV)
    assert pending[0]["tool"] == "run_automation"
    assert pending[0]["source"] == "api"
    assert "a1" in pending[0]["label"]
    assert host.automation_runs == [], "automation queued before approval"

    host.confirm_action(pending[0]["id"], True, approver="tester", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "ok"
    assert "run-1" in body["result"]
    assert host.automation_runs == [("a1", DEV)]


# ------------------------------------------------- autonomous mode + the opt-in
def test_autonomous_with_exact_optin_auto_approves(host, tc):
    host.set_agent_mode(DEV, "autonomous")
    h = _key(host, ["devices:command", "mcp:autonomous"])
    r = tc.post("/api/v1/actions/invoke", headers=h,
                json={"device_id": DEV, "action": "tap", "args": {"x": 5, "y": 6}})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok" and "Tapped" in body["result"]
    assert host.clicks == [(5, 6, DEV)]
    # No gate pause: nothing pending, no pending_action broadcast ever fired.
    assert host.list_pending_actions(DEV) == []
    assert not any(e == "pending_action" for e, _ in host.broadcasts)
    # The auto-approval is still audited.
    assert any(a["decision"] == "auto" and a["tool"] == "tap"
               for a in host.get_agent_audit(DEV))


def test_autonomous_without_optin_is_forced_through_gate(host, app):
    host.set_agent_mode(DEV, "autonomous")
    h = _key(host, ["devices:command"])
    t, box = _invoke_async(app, {"device_id": DEV, "action": "tap",
                                 "args": {"x": 7, "y": 8}}, headers=h)
    pending = _wait_pending(host, DEV)
    assert pending[0]["source"] == "api"
    assert host.clicks == [], "key without mcp:autonomous auto-ran on autonomous device"
    host.confirm_action(pending[0]["id"], False, approver="tester", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "denied"
    assert host.clicks == []


def test_wildcard_scope_does_not_grant_autonomy(host, app):
    # '*' passes every scope check but is NOT the exact mcp:autonomous token.
    host.set_agent_mode(DEV, "autonomous")
    h = _key(host, ["*"])
    t, box = _invoke_async(app, {"device_id": DEV, "action": "tap",
                                 "args": {"x": 9, "y": 9}}, headers=h)
    pending = _wait_pending(host, DEV)
    assert pending[0]["tool"] == "tap"
    assert host.clicks == [], "wildcard key bypassed the forced gate"
    host.confirm_action(pending[0]["id"], False, approver="tester", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "denied"
    assert host.clicks == []


# --------------------------------------------------------- sessions & timeouts
def test_viewer_session_cannot_invoke_writes(host, tc):
    """/actions isn't feature-mapped centrally, so the route must fold the action class
    onto the role matrix itself — a read-only user gets no side door to hardware writes."""
    host.create_user("admin", "pw", role="admin")
    viewer = host.create_user("viewer", "pw", role="viewer")
    token = host.create_session(viewer["id"])
    h = {"X-Session-Token": token}

    r = tc.post("/api/v1/actions/invoke", headers=h,
                json={"device_id": DEV, "action": "tap", "args": {"x": 1, "y": 2}})
    assert r.status_code == 403
    assert host.clicks == []
    r = tc.post("/actions/invoke", headers=h,
                json={"device_id": DEV, "action": "run_automation",
                      "args": {"automation_id": "a1"}})
    assert r.status_code == 403
    assert host.automation_runs == []
    # Reads stay open to viewers, matching the rest of the API.
    r = tc.post("/api/v1/actions/invoke", headers=h,
                json={"device_id": DEV, "action": "get_battery", "args": {}})
    assert r.status_code == 200 and r.get_json()["status"] == "ok"


def test_operator_session_matches_direct_route_matrix(host, app, tc):
    """Operator role: automations write yes, devices write no — the invoke fold must
    mirror the direct routes (tap denied, run_automation allowed but still gated)."""
    host.create_user("admin", "pw", role="admin")
    operator = host.create_user("op", "pw", role="operator")
    token = host.create_session(operator["id"])
    h = {"X-Session-Token": token}

    r = tc.post("/api/v1/actions/invoke", headers=h,
                json={"device_id": DEV, "action": "tap", "args": {"x": 2, "y": 3}})
    assert r.status_code == 403
    assert host.clicks == []

    t, box = _invoke_async(app, {"device_id": DEV, "action": "run_automation",
                                 "args": {"automation_id": "a2"}}, headers=h)
    pending = _wait_pending(host, DEV)
    host.confirm_action(pending[0]["id"], True, approver="op", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "ok"
    assert host.automation_runs == [("a2", DEV)]


def test_solo_session_supervised_still_gates(host, app):
    # Solo principal (scopes None): force_gate is off, but supervised mode gates anyway.
    t, box = _invoke_async(app, {"device_id": DEV, "action": "tap",
                                 "args": {"x": 1, "y": 2}})
    pending = _wait_pending(host, DEV)
    assert pending[0]["source"] == "api"
    assert host.clicks == []
    host.confirm_action(pending[0]["id"], True, approver="solo", device_id=DEV)
    body = _finish(t, box)
    assert body["status"] == "ok"
    assert host.clicks == [(1, 2, DEV)]


def test_gate_timeout_returns_denied(host, tc):
    host._gate_timeout = 1
    start = time.time()
    r = tc.post("/api/v1/actions/invoke",
                json={"device_id": DEV, "action": "tap", "args": {"x": 1, "y": 1}})
    elapsed = time.time() - start
    assert elapsed >= 1, "gate did not wait for the timeout"
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "denied"
    assert "timed out" in body["result"]
    assert host.clicks == []
    assert host.list_pending_actions(DEV) == []
