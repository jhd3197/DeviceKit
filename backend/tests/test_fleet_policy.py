"""FleetPolicy persistence + lifecycle + HTTP surface (plan 23 phase 2)."""
import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.fleet_policy import FleetPolicyMixin
from devicekit.mixins.workspaces import WorkspacesMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.policy.spec import PolicySpecError
from devicekit.services.gate import authorize
from devicekit.routes import fleet_policies as policy_routes

YAML_ONE = """
version: 1
name: samsung-baseline
target: {device: SER1}
settings:
  system: {screen_brightness: 128}
"""

YAML_TWO = YAML_ONE.replace("128", "255")


class _PolicyClient(FleetPolicyMixin, WorkspacesMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None

    def broadcast(self, event_type, data):  # SSE seam not composed in this test client
        pass


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _PolicyClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- persistence
def test_create_persists_raw_normalized_hash_status(client):
    p = client.create_fleet_policy(YAML_ONE)
    assert p["status"] == "pending"
    assert p["name"] == "samsung-baseline"          # from spec
    assert p["target_kind"] == "device" and p["target_value"] == "SER1"
    assert len(p["policy_hash"]) == 64
    assert p["raw_yaml"] == YAML_ONE                # raw text kept verbatim
    assert p["normalized"]["settings"]["system"]["screen_brightness"] == 128
    assert p["auto_apply"] is False


def test_survives_restart(client, fresh_db, restart):
    p = client.create_fleet_policy(YAML_ONE)
    restart(fresh_db)
    again = client.get_fleet_policy(p["id"])
    assert again["policy_hash"] == p["policy_hash"]
    assert again["raw_yaml"] == YAML_ONE


def test_update_yaml_change_flips_to_pending(client):
    p = client.create_fleet_policy(YAML_ONE)
    client._set_policy_status(p["id"], "applied")
    updated = client.update_fleet_policy(p["id"], yaml_text=YAML_TWO)
    assert updated["status"] == "pending"
    assert updated["policy_hash"] != p["policy_hash"]
    # applied_hash survives the edit so drift/idempotence can compare revisions.
    assert updated["applied_hash"] == p["policy_hash"]


def test_update_unchanged_yaml_keeps_status(client):
    p = client.create_fleet_policy(YAML_ONE)
    client._set_policy_status(p["id"], "applied")
    updated = client.update_fleet_policy(p["id"], yaml_text=YAML_ONE)
    assert updated["status"] == "applied"


def test_invalid_yaml_raises_and_never_persists(client):
    with pytest.raises(PolicySpecError):
        client.create_fleet_policy("version: 1\n")   # no target
    assert client.list_fleet_policies() == []


def test_delete(client):
    p = client.create_fleet_policy(YAML_ONE)
    assert client.delete_fleet_policy(p["id"]) is True
    assert client.get_fleet_policy(p["id"]) is None
    with pytest.raises(ValueError):
        client.delete_fleet_policy(p["id"])


def test_workspace_scoping(client):
    ws = client.create_workspace("Team", created_by=None)
    client.create_fleet_policy(YAML_ONE)
    client.create_fleet_policy(YAML_TWO, name="ws-policy", workspace_id=ws["id"])
    assert len(client.list_fleet_policies()) == 2
    scoped = client.list_fleet_policies(workspace_id=ws["id"])
    assert [p["name"] for p in scoped] == ["ws-policy"]


def test_auto_apply_param_overrides_spec(client):
    p = client.create_fleet_policy(YAML_ONE, auto_apply=True)
    assert p["auto_apply"] is True
    p2 = client.update_fleet_policy(p["id"], auto_apply=False)
    assert p2["auto_apply"] is False


# --------------------------------------------------------------- HTTP
@pytest.fixture
def http(client):
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(policy_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    return app.test_client()


def test_http_crud_and_validate(http):
    r = http.post("/fleet-policies", json={"yaml": YAML_ONE})
    assert r.status_code == 201
    policy = r.get_json()["policy"]

    listed = http.get("/fleet-policies").get_json()
    assert listed["count"] == 1 and listed["policies"][0]["id"] == policy["id"]
    assert "raw_yaml" not in listed["policies"][0]   # list stays light

    detail = http.get(f"/fleet-policies/{policy['id']}").get_json()["policy"]
    assert detail["raw_yaml"] == YAML_ONE

    bad = http.post("/fleet-policies", json={"yaml": "version: 1\n"})
    assert bad.status_code == 400 and bad.get_json()["errors"]

    ok = http.post("/fleet-policies/validate", json={"yaml": YAML_ONE}).get_json()
    assert ok["valid"] is True and ok["policy_hash"]
    nok = http.post("/fleet-policies/validate", json={"yaml": "nope"}).get_json()
    assert nok["valid"] is False and nok["errors"]

    assert http.put(f"/fleet-policies/{policy['id']}",
                    json={"yaml": YAML_TWO}).get_json()["policy"]["status"] == "pending"
    assert http.delete(f"/fleet-policies/{policy['id']}").status_code == 200
    assert http.get(f"/fleet-policies/{policy['id']}").status_code == 404


def test_http_viewer_forbidden_to_write(http, client):
    client.create_user("v", "pw123456", role="viewer")
    tok = client.create_session(client.list_users()[0]["id"])
    h = {"X-Session-Token": tok}
    # /fleet-policies falls under the /fleet -> devices feature: viewers read, never write.
    assert http.get("/fleet-policies", headers=h).status_code == 200
    assert http.post("/fleet-policies", headers=h,
                     json={"yaml": YAML_ONE}).status_code == 403


# --------------------------------------------------------------- plan (phase 3)
class _StubbedClient(_PolicyClient):
    """FleetPolicyMixin over canned live seams: one ADB device SER1 with brightness 40,
    the VPN app absent, an existing automation with no schedule, and the vpn extension
    active with an APK supplied."""

    adb_log = None

    def all_devices_for_query(self):
        return [{"serial": "SER1", "device_id": "SER1", "online": True},
                {"serial": "AGENT9", "device_id": "AGENT9", "online": True,
                 "source": "agent"}]

    def get_device_group(self, group_id):
        return {"id": group_id, "device_ids": ["SER1"]} if group_id == "grp-1" else None

    def execute_fleet_query(self, expression, devices=None):
        return [d for d in devices or [] if d.get("source") != "agent"]

    def get_extension(self, slug):
        if slug != "devicekit-vpn":
            return None
        return {"slug": slug, "status": "active", "manifest": {"device_requirements": {
            "package": "com.expressvpn.vpn", "supported_versions": ">=12",
            "provision": "user_supplied_apk"}}}

    def get_extension_config_raw(self, slug):
        return {"apk_b64": "QUJD", "apk_version": "12.4.0"}

    def get_extension_registry(self, force=False):
        return [{"slug": "devicekit-vpn"}]

    def get_automation(self, automation_id):
        return None

    def list_automations(self, workspace_id=None):
        return [{"id": "a1", "name": "auto-1"}]

    def list_schedules(self, automation_id=None):
        return []

    def run_adb_command(self, args, device=None):
        (self.adb_log if self.adb_log is not None else []).append((device, args))
        if args[:3] == ["shell", "dumpsys", "package"]:
            return ""                                   # app not installed
        if args[:3] == ["shell", "settings", "get"]:
            return "40"
        return ""


POLICY_YAML = """
version: 1
target: {device: SER1}
apps:
  - {package: com.expressvpn.vpn, version: "12.4.0", extension: devicekit-vpn}
automations:
  - {automation: auto-1, schedule: {intervalMinutes: 30}}
settings:
  system: {screen_brightness: 128}
extensions: [devicekit-vpn]
"""


@pytest.fixture
def stubbed(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _StubbedClient()
    c.adb_log = []
    c.init_identity()
    return c


def test_plan_end_to_end_over_stub_seams(stubbed):
    p = stubbed.create_fleet_policy(POLICY_YAML)
    plan = stubbed.plan_fleet_policy(p["id"])
    assert plan["blockers"] == []
    assert [s["kind"] for s in plan["steps"]] == [
        "provision_app", "configure_setting", "enable_automation"]
    assert plan["steps"][0]["desired_version"] == "12.4.0"
    assert plan["steps"][1]["current"] == "40" and plan["steps"][1]["value"] == "128"
    assert plan["steps"][2]["automation_id"] == "a1"    # resolved by name
    # Live reads went to the right device over ADB.
    assert all(dev == "SER1" for dev, _ in stubbed.adb_log)


def test_plan_group_and_fql_targets_resolve(stubbed):
    grp = stubbed.create_fleet_policy("version: 1\ntarget: {group: grp-1}\n")
    assert stubbed.plan_fleet_policy(grp["id"])["devices"] == ["SER1"]
    fql = stubbed.create_fleet_policy("version: 1\ntarget: {fql: 'online = true'}\n")
    assert stubbed.plan_fleet_policy(fql["id"])["devices"] == ["SER1"]
    missing = stubbed.create_fleet_policy("version: 1\ntarget: {group: nope}\n")
    with pytest.raises(ValueError):
        stubbed.plan_fleet_policy(missing["id"])


def test_plan_agent_only_device_blocks_on_adb(stubbed):
    p = stubbed.create_fleet_policy(POLICY_YAML.replace("SER1", "AGENT9"))
    plan = stubbed.plan_fleet_policy(p["id"])
    assert [b["code"] for b in plan["blockers"]] == ["adb_required"]


def test_plan_resolves_fromsecret_through_vault(fresh_db, monkeypatch):
    from devicekit.mixins.vault import VaultMixin

    class _VaultedClient(VaultMixin, _StubbedClient):
        pass

    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _VaultedClient()
    c.adb_log = []
    c.init_identity()
    vault = c.create_vault("Fleet", slug="fleet")
    c.set_secret(vault["id"], "PIN", "40")     # matches the stub's live value "40"
    p = c.create_fleet_policy("""
version: 1
target: {device: SER1}
settings:
  system:
    lock_pin: {fromSecret: {vault: fleet, key: PIN}}
""")
    assert c.plan_fleet_policy(p["id"])["empty"] is True

    c.set_secret(vault["id"], "PIN", "9999")   # rotate → drift → masked step
    plan = c.plan_fleet_policy(p["id"])
    assert plan["steps"][0]["value"] == "••••••" and "9999" not in str(plan)


def test_http_plan_route(http, client, monkeypatch):
    monkeypatch.setattr(_PolicyClient, "plan_fleet_policy",
                        lambda self, pid: {"steps": [], "issues": [], "blockers": [],
                                           "devices": [], "empty": True,
                                           "policy_id": pid}, raising=False)
    p = http.post("/fleet-policies", json={"yaml": YAML_ONE}).get_json()["policy"]
    r = http.get(f"/fleet-policies/{p['id']}/plan")
    assert r.status_code == 200 and r.get_json()["plan"]["empty"] is True
