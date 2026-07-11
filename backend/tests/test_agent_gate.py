"""AI confirmation gate, session modes, and audit trail (plan 13).

Exercises the gate without a live device or provider: build a gated tool over a fake
callable and drive it on a worker thread while the "human" approves/denies from the test
thread — exactly how the agent loop thread blocks while a Flask request releases the gate.
Also covers observe-mode tool filtering, the autonomous auto-approve path, per-device mode
default from the profile, audit persistence across a restart, and the HTTP endpoints.
"""
import threading
import time

import pytest
from flask import Flask
from prompture import ToolRegistry

from devicekit.mixins.agent_gate import AgentGateMixin
from devicekit.mixins.prompture_agent import (
    PromptureAgentMixin, build_device_tools, _gate_write_tool)
from devicekit.mixins.profile import ProfileMixin
from devicekit.mixins.settings import SettingsMixin
from devicekit.mixins.events import EventsMixin
from devicekit.mixins.activity import ActivityMixin
from devicekit.routes import ai_agent

DEV = "GATEDEV"


class _GateClient(AgentGateMixin, PromptureAgentMixin, ProfileMixin,
                  SettingsMixin, ActivityMixin, EventsMixin):
    """Minimal composition exercising the gate without booting the full Client (which would
    re-initialize the engine off the test's temp DB)."""


@pytest.fixture
def client(fresh_db):
    c = _GateClient()
    # These mixins default their state as shared class attrs — give each test its own so
    # profiles / modes / conversations don't bleed between tests.
    c._profiles = []
    c._agent_conversations = {}
    c._ensure_gate()
    return c


def _gated_registry(client, device_id, real_fn, name="uninstall_app"):
    reg = ToolRegistry()
    meta = {"is_write": True, "category": "app", "label": "Uninstall app"}
    td = reg.register(real_fn, name=name, metadata=meta)
    _gate_write_tool(client, device_id, td, meta, source="core")
    return reg


def _call_in_thread(reg, name, args, box, key):
    def run():
        box[key] = reg.execute(name, args)
    t = threading.Thread(target=run)
    t.start()
    return t


# --------------------------------------------------------------------------- modes
def test_observe_filters_out_write_tools(client):
    observe = build_device_tools(client, DEV, mode="observe")
    supervised = build_device_tools(client, DEV, mode="supervised")
    # Every observe tool is a read tool; no write tool leaks in.
    assert observe.names
    assert all(observe.get(n).metadata.get("is_write") is False for n in observe.names)
    # Write tools exist under supervised but not observe.
    assert "uninstall_app" in supervised.names
    assert "uninstall_app" not in observe.names
    assert "tap" not in observe.names


def test_mode_default_from_profile(client):
    client.create_profile(DEV, "p", agent_mode="autonomous")
    assert client.get_agent_mode(DEV) == "autonomous"
    # Explicit session override wins over the profile default.
    client.set_agent_mode(DEV, "observe")
    assert client.get_agent_mode(DEV) == "observe"


def test_invalid_mode_rejected(client):
    assert "error" in client.set_agent_mode(DEV, "bogus")


# --------------------------------------------------------------------------- the gate
def test_supervised_gate_blocks_until_approved(client):
    client.set_agent_mode(DEV, "supervised")
    executed = {}
    reg = _gated_registry(client, DEV, lambda package: executed.setdefault("pkg", package) or "ok")

    box = {}
    t = _call_in_thread(reg, "uninstall_app", {"package": "com.instagram.android"}, box, "r")
    time.sleep(0.3)
    pending = client.list_pending_actions(DEV)
    assert len(pending) == 1
    assert "instagram" in pending[0]["summary"]
    assert executed == {}, "tool ran before approval"

    client.confirm_action(pending[0]["id"], True, approver="tester", device_id=DEV)
    t.join(timeout=3)
    assert executed["pkg"] == "com.instagram.android"
    assert client.list_pending_actions(DEV) == []


def test_supervised_gate_denies(client):
    client.set_agent_mode(DEV, "supervised")
    executed = {}
    reg = _gated_registry(client, DEV, lambda package: executed.setdefault("pkg", package) or "ok")

    box = {}
    t = _call_in_thread(reg, "uninstall_app", {"package": "com.x"}, box, "r")
    time.sleep(0.3)
    pending = client.list_pending_actions(DEV)
    client.confirm_action(pending[0]["id"], False, approver="tester", device_id=DEV)
    t.join(timeout=3)
    assert executed == {}, "denied tool must not run"
    assert "DENIED" in box["r"]


def test_gate_timeout_default_denies(client, monkeypatch):
    client.set_agent_mode(DEV, "supervised")
    monkeypatch.setattr(client, "ai_gate_timeout_seconds", lambda: 1)
    executed = {}
    reg = _gated_registry(client, DEV, lambda package: executed.setdefault("pkg", package) or "ok")

    box = {}
    t = _call_in_thread(reg, "uninstall_app", {"package": "com.x"}, box, "r")
    t.join(timeout=4)
    assert executed == {}, "timed-out action must not run"
    assert "timed out" in box["r"].lower()
    audit = client.get_agent_audit(DEV)
    assert any(a["decision"] == "timeout" for a in audit)


def test_autonomous_auto_approves(client):
    client.set_agent_mode(DEV, "autonomous")
    executed = {}

    def fake(package):
        executed["pkg"] = package
        return "ok"

    reg = _gated_registry(client, DEV, fake)
    result = reg.execute("uninstall_app", {"package": "com.auto"})
    assert executed["pkg"] == "com.auto"
    assert result == "ok"
    assert client.list_pending_actions(DEV) == []
    assert any(a["decision"] == "auto" for a in client.get_agent_audit(DEV))


def test_confirm_unknown_action(client):
    assert "error" in client.confirm_action("nope", True, device_id=DEV)


# --------------------------------------------------------------------------- audit
def test_audit_persists_across_restart(client, fresh_db, restart):
    client.set_agent_mode(DEV, "autonomous")
    reg = _gated_registry(client, DEV, lambda package: "ok")
    reg.execute("uninstall_app", {"package": "com.persist"})
    assert client.get_agent_audit(DEV)

    restart(fresh_db)
    client2 = _GateClient()
    rows = client2.get_agent_audit(DEV)
    assert len(rows) == 1
    assert rows[0]["tool"] == "uninstall_app"
    assert rows[0]["args"] == {"package": "com.persist"}
    assert rows[0]["decision"] == "auto"


# --------------------------------------------------------------------------- HTTP
def test_gate_http_endpoints(client):
    app = Flask(__name__)
    app.register_blueprint(ai_agent.make_blueprint(client, None))
    c = app.test_client()

    # mode PUT/GET
    assert c.put(f"/devices/{DEV}/agent/mode", json={"mode": "supervised"}).status_code == 200
    assert c.get(f"/devices/{DEV}/agent/mode").get_json()["mode"] == "supervised"
    assert c.put(f"/devices/{DEV}/agent/mode", json={"mode": "bogus"}).status_code == 400

    executed = {}
    reg = _gated_registry(client, DEV, lambda package: executed.setdefault("pkg", package) or "ok")
    box = {}
    t = _call_in_thread(reg, "uninstall_app", {"package": "com.http"}, box, "r")
    time.sleep(0.3)

    pending = c.get(f"/devices/{DEV}/agent/pending").get_json()
    assert pending["count"] == 1
    action_id = pending["pending_actions"][0]["id"]

    # unknown action -> 404
    assert c.post(f"/devices/{DEV}/agent/confirm", json={"action_id": "x"}).status_code == 404
    # approve releases the gate
    assert c.post(f"/devices/{DEV}/agent/confirm",
                  json={"action_id": action_id, "approve": True}).status_code == 200
    t.join(timeout=3)
    assert executed["pkg"] == "com.http"

    audit = c.get(f"/devices/{DEV}/agent/audit").get_json()
    assert audit["count"] == 1
    assert audit["audit"][0]["decision"] == "approved"


# --------------------------------------------------------------------------- extensions (ph3)
def _with_ext_tools(client, entries):
    """Attach fake extension AI tools + an always-active status guard."""
    client._ext_ai_tools = {"demo": entries}
    client.get_extension = lambda slug: {"status": "active"}


def test_sdk_binder_threads_is_write():
    import devicekit_sdk

    class _Host:
        def __init__(self):
            self.calls = []
        def _register_ai_tool(self, slug, name, func, description, is_write=True):
            self.calls.append((name, is_write))

    host = _Host()
    devicekit_sdk.set_host(host)
    binder = devicekit_sdk.ai("demo")

    @binder.tool
    def act():
        """A write tool."""

    @binder.tool(is_write=False)
    def look():
        """A read tool."""

    assert ("act", True) in host.calls
    assert ("look", False) in host.calls


def test_extension_read_tool_not_gated_write_tool_gated(client):
    ran = {}

    def look():
        ran["look"] = True
        return "seen"

    def wipe():
        ran["wipe"] = True
        return "gone"

    _with_ext_tools(client, [
        ("look", look, "Read", False),
        ("wipe", wipe, "Write", True),
    ])
    client.set_agent_mode(DEV, "autonomous")
    reg = build_device_tools(client, DEV, mode="autonomous")

    # Read extension tool runs free even in autonomous.
    assert reg.execute("demo__look", {}) == "seen"
    assert ran.get("look")

    # Write extension tool is ALWAYS gated (always_gate), even under autonomous — so it
    # creates a pending action and does not run synchronously.
    box = {}
    t = _call_in_thread(reg, "demo__wipe", {}, box, "r")
    time.sleep(0.3)
    pending = client.list_pending_actions(DEV)
    assert len(pending) == 1
    assert pending[0]["source"] == "extension:demo"
    assert "wipe" not in ran, "extension write tool ran without approval under autonomous"
    client.confirm_action(pending[0]["id"], True, approver="t", device_id=DEV)
    t.join(timeout=3)
    assert ran.get("wipe")


def test_extension_write_hidden_in_observe(client):
    _with_ext_tools(client, [
        ("look", lambda: "seen", "Read", False),
        ("wipe", lambda: "gone", "Write", True),
    ])
    reg = build_device_tools(client, DEV, mode="observe")
    assert "demo__look" in reg.names
    assert "demo__wipe" not in reg.names


def test_observe_direct_write_is_denied(client):
    """A write reaching the gate directly (e.g. self-heal) is refused in observe mode."""
    client.set_agent_mode(DEV, "observe")
    ran = {}
    msg = client.gate_tool_call(
        DEV, "self_heal", {"x": 1},
        {"is_write": True, "category": "self_heal", "label": "Apply self-heal"},
        source="self_heal", real_fn=lambda x: ran.setdefault("ran", True))
    assert "DENIED" in msg
    assert ran == {}
    assert any(a["decision"] == "denied" and a["source"] == "self_heal"
               for a in client.get_agent_audit(DEV))
