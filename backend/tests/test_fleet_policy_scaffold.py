"""Scaffold: devicekit.yaml from live state, secrets never inline (plan 23 phase 6)."""
import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.policy.scaffold import render_scaffold
from devicekit.policy.spec import load_policy
from devicekit.routes import fleet_policies as policy_routes
from devicekit.services.gate import authorize

from test_fleet_policy import _PolicyClient

VPN_EXT = {"slug": "devicekit-vpn", "status": "active", "manifest": {
    "device_requirements": {"package": "com.expressvpn.vpn",
                            "supported_versions": ">=12",
                            "provision": "user_supplied_apk"}}}


class _ScaffoldClient(_PolicyClient):
    """One ADB device (SER1: vpn app 12.4.0, brightness 40, a 30-min schedule) and one
    agent-only device (AGENT9)."""

    def all_devices_for_query(self):
        return [{"serial": "SER1", "device_id": "SER1", "online": True},
                {"serial": "AGENT9", "device_id": "AGENT9", "online": True,
                 "source": "agent"}]

    def list_extensions(self):
        return [VPN_EXT]

    def get_extension(self, slug):
        return VPN_EXT if slug == "devicekit-vpn" else None

    def get_extension_config_raw(self, slug):
        return {"apk_b64": "QUJD", "apk_version": "12.4.0"}

    def get_extension_registry(self, force=False):
        return [{"slug": "devicekit-vpn"}]

    def get_automation(self, automation_id):
        return None

    def list_automations(self, workspace_id=None):
        return [{"id": "a1", "name": "cleanup"}]

    def list_schedules(self, automation_id=None):
        return [{"id": "sch1", "automation_id": "a1", "automation_name": "cleanup",
                 "device_id": "SER1", "interval_minutes": 30, "enabled": True}]

    def run_adb_command(self, args, device=None):
        if args[:3] == ["shell", "dumpsys", "package"]:
            return "versionName=12.4.0" if args[3] == "com.expressvpn.vpn" else ""
        if args[:3] == ["shell", "settings", "get"]:
            return "40" if args[4] == "screen_brightness" else "null"
        return ""


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _ScaffoldClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- pure renderer
def test_sensitive_settings_are_redacted_to_refs():
    out = render_scaffold("SER1", {"settings": {"system": {
        "lock_pin": "1234", "wifi_password": "hunter2", "screen_brightness": "40"}}})
    assert "1234" not in out["yaml"] and "hunter2" not in out["yaml"]
    system = out["spec"]["settings"]["system"]
    assert system["lock_pin"]["fromSecret"] == {
        "vault": "fleet-secrets", "key": "LOCK_PIN"}
    assert system["wifi_password"]["fromSecret"]["key"] == "WIFI_PASSWORD"
    assert system["screen_brightness"] == "40"        # non-sensitive stays literal
    assert {r["secret_key"] for r in out["redactions"]} == {"LOCK_PIN", "WIFI_PASSWORD"}
    # Scaffold never sets generate — applying must not silently rotate a live credential.
    assert "generate" not in out["yaml"]
    load_policy(out["yaml"])                          # guaranteed loadable


# --------------------------------------------------------------- adopt round-trip
def test_scaffold_captures_live_state(client):
    out = client.scaffold_fleet_policy("SER1", name="samsung-adopt")
    spec = out["spec"]
    assert spec["target"] == {"device": "SER1"}
    assert spec["apps"] == [{"package": "com.expressvpn.vpn", "version": "12.4.0",
                             "extension": "devicekit-vpn"}]
    assert spec["automations"] == [{"automation": "cleanup", "enabled": True,
                                    "schedule": {"intervalMinutes": 30}}]
    assert spec["settings"]["system"]["screen_brightness"] == "40"
    assert spec["extensions"] == ["devicekit-vpn"]
    assert out["issues"] == [] and out["redactions"] == []


def test_adopted_scaffold_plans_empty(client):
    """The headline guarantee: scaffold a device, adopt the YAML, and the first plan is
    empty — the policy really describes what the device already looks like."""
    out = client.scaffold_fleet_policy("SER1")
    policy = client.create_fleet_policy(out["yaml"])
    assert policy["status"] == "pending"
    plan = client.plan_fleet_policy(policy["id"])
    assert plan["empty"] is True, plan


def test_agent_only_device_scaffolds_partial_with_issue(client):
    out = client.scaffold_fleet_policy("AGENT9")
    assert out["spec"]["apps"] == [] and out["spec"]["settings"] == {}
    assert out["spec"]["extensions"] == ["devicekit-vpn"]   # global facts still captured
    assert any("ADB" in issue for issue in out["issues"])


def test_unknown_device_raises(client):
    with pytest.raises(ValueError):
        client.scaffold_fleet_policy("NOPE")


# --------------------------------------------------------------- HTTP
def test_http_scaffold_and_save(client):
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[],
                      storage_uri="memory://")
    app.register_blueprint(policy_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc = app.test_client()
    assert tc.post("/fleet-policies/scaffold", json={}).status_code == 400
    assert tc.post("/fleet-policies/scaffold",
                   json={"device_id": "NOPE"}).status_code == 404

    r = tc.post("/fleet-policies/scaffold", json={"device_id": "SER1"})
    assert r.status_code == 200 and "com.expressvpn.vpn" in r.get_json()["yaml"]

    saved = tc.post("/fleet-policies/scaffold",
                    json={"device_id": "SER1", "save": True, "name": "adopted"})
    assert saved.status_code == 201
    policy = saved.get_json()["policy"]
    assert policy["name"] == "adopted" and policy["status"] == "pending"
    assert tc.get("/fleet-policies").get_json()["count"] == 1
