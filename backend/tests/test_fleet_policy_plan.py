"""Policy planner: pure diff, step ordering, honesty-rule blockers (plan 23 phase 3)."""
import pytest

from devicekit.policy.planner import plan_policy
from devicekit.policy.spec import load_policy

SER = "SER1"

FULL_YAML = """
version: 1
target: {device: SER1}
apps:
  - package: com.expressvpn.vpn
    version: "12.4.0"
    extension: devicekit-vpn
automations:
  - automation: auto-1
    schedule: {intervalMinutes: 30}
settings:
  system: {screen_brightness: 128}
extensions: [devicekit-vpn]
"""


def _live(**over):
    """A live snapshot where everything already matches FULL_YAML (empty plan)."""
    live = {
        "devices": {SER: {
            "present": True, "online": True, "adb": True,
            "apps": {"com.expressvpn.vpn": "12.4.0"},
            "settings": {"system": {"screen_brightness": "128"}},
            "automations": {"auto-1": {
                "automation_id": "a1",
                "schedule": {"id": "sch1", "interval_minutes": 30, "enabled": True}}},
        }},
        "app_meta": {"devicekit-vpn": {
            "installed": True, "active": True, "supported_versions": ">=12",
            "provision": "user_supplied_apk", "apk_supplied": True,
            "apk_version": "12.4.0"}},
        "extensions": {"devicekit-vpn": {
            "installed": True, "active": True, "available": True}},
        "secrets": {},
    }
    live.update(over)
    return live


def _device(live, **over):
    live["devices"][SER] = {**live["devices"][SER], **over}
    return live


def test_matching_state_yields_empty_plan():
    plan = plan_policy(load_policy(FULL_YAML), [SER], _live())
    assert plan["empty"] is True
    assert plan["steps"] == [] and plan["blockers"] == []


def test_full_divergence_orders_steps_by_weight_map():
    live = _live()
    _device(live, apps={"com.expressvpn.vpn": None},
            settings={"system": {"screen_brightness": "40"}},
            automations={"auto-1": {"automation_id": "a1", "schedule": None}})
    live["extensions"]["devicekit-vpn"] = {
        "installed": True, "active": False, "available": True}
    live["app_meta"]["devicekit-vpn"]["active"] = False
    plan = plan_policy(load_policy(FULL_YAML), [SER], live)
    kinds = [s["kind"] for s in plan["steps"]]
    # Extension attaches FIRST (deviation from ServerKit order: provisioning rides it).
    assert kinds == ["attach_extension", "provision_app", "configure_setting",
                     "enable_automation"]
    assert plan["steps"][0]["device_id"] is None      # global step
    assert plan["steps"][0]["action"] == "enable"
    assert plan["blockers"] == []                     # declared ext → no blocker
    assert any(i["code"] == "extension_pending" for i in plan["issues"])


def test_version_range_pin_uses_range_semantics():
    live = _device(_live(), apps={"com.expressvpn.vpn": "12.9.1"})
    spec = load_policy(FULL_YAML.replace('"12.4.0"', '">=12.4"'))
    assert plan_policy(spec, [SER], live)["empty"] is True


# --------------------------------------------------------------- blockers (honesty rule)
@pytest.mark.parametrize("mutate,code", [
    (lambda l: _device(l, present=False), "device_missing"),
    (lambda l: _device(l, online=False), "device_offline"),
    (lambda l: _device(l, adb=False), "adb_required"),
])
def test_device_level_blockers(mutate, code):
    plan = plan_policy(load_policy(FULL_YAML), [SER], mutate(_live()))
    assert [b["code"] for b in plan["blockers"]] == [code]
    assert plan["steps"] == [] and plan["empty"] is False


def _diverged(**meta_over):
    live = _device(_live(), apps={"com.expressvpn.vpn": None})
    live["app_meta"]["devicekit-vpn"].update(meta_over)
    return live


@pytest.mark.parametrize("meta,code", [
    ({"apk_supplied": False}, "apk_unsupplied"),
    ({"provision": "play_store"}, "manual_install_required"),
    ({"apk_version": "11.0.0"}, "apk_version_mismatch"),
    ({"supported_versions": ">=13"}, "version_unsupported"),
])
def test_app_blockers(meta, code):
    plan = plan_policy(load_policy(FULL_YAML), [SER], _diverged(**meta))
    assert code in [b["code"] for b in plan["blockers"]]
    assert not any(s["kind"] == "provision_app" for s in plan["steps"])


def test_undeclared_missing_extension_blocks():
    live = _diverged(active=False, installed=False)
    spec = load_policy(FULL_YAML.replace("extensions: [devicekit-vpn]", ""))
    plan = plan_policy(spec, [SER], live)
    assert "extension_missing" in [b["code"] for b in plan["blockers"]]


def test_app_without_extension_has_no_provision_path():
    spec = load_policy("""
version: 1
target: {device: SER1}
apps: [{package: com.some.app}]
""")
    live = _device(_live(), apps={"com.some.app": None})
    plan = plan_policy(spec, [SER], live)
    assert [b["code"] for b in plan["blockers"]] == ["no_provision_path"]


def test_unavailable_extension_blocks():
    live = _live()
    live["extensions"]["devicekit-vpn"] = {
        "installed": False, "active": False, "available": False}
    plan = plan_policy(load_policy(FULL_YAML), [SER], live)
    assert "extension_unavailable" in [b["code"] for b in plan["blockers"]]


def test_automation_missing_blocks():
    live = _device(_live(), automations={"auto-1": {"automation_id": None}})
    plan = plan_policy(load_policy(FULL_YAML), [SER], live)
    assert "automation_missing" in [b["code"] for b in plan["blockers"]]


def test_secret_ref_missing_blocks_but_generate_plans():
    spec = load_policy("""
version: 1
target: {device: SER1}
settings:
  system:
    wifi_psk: {fromSecret: {vault: v1, key: PSK}}
""")
    live = _live()
    live["secrets"] = {"v1/PSK": {"found": False, "value": None}}
    plan = plan_policy(spec, [SER], live)
    assert [b["code"] for b in plan["blockers"]] == ["secret_missing"]

    gen = load_policy("""
version: 1
target: {device: SER1}
settings:
  system:
    wifi_psk: {fromSecret: {vault: v1, key: PSK}, generate: true}
""")
    plan = plan_policy(gen, [SER], live)
    assert plan["blockers"] == []
    step = plan["steps"][0]
    assert step["generate"] is True and step["value"] == "••••••"   # never inline


def test_secret_value_masked_and_diffed():
    spec = load_policy("""
version: 1
target: {device: SER1}
settings:
  system:
    wifi_psk: {fromSecret: {vault: v1, key: PSK}}
""")
    live = _live()
    live["secrets"] = {"v1/PSK": {"found": True, "value": "hunter2"}}
    live["devices"][SER]["settings"] = {"system": {"wifi_psk": "hunter2"}}
    assert plan_policy(spec, [SER], live)["empty"] is True
    live["devices"][SER]["settings"] = {"system": {"wifi_psk": "old"}}
    plan = plan_policy(spec, [SER], live)
    step = plan["steps"][0]
    assert step["value"] == "••••••" and "hunter2" not in str(plan)


def test_schedule_update_and_disable():
    live = _device(_live(), automations={"auto-1": {
        "automation_id": "a1",
        "schedule": {"id": "sch1", "interval_minutes": 15, "enabled": True}}})
    plan = plan_policy(load_policy(FULL_YAML), [SER], live)
    step = [s for s in plan["steps"] if s["kind"] == "enable_automation"][0]
    assert step["action"] == "update" and step["interval_minutes"] == 30

    disabled = load_policy(FULL_YAML.replace(
        "schedule: {intervalMinutes: 30}",
        "schedule: {intervalMinutes: 30}\n    enabled: false"))
    plan = plan_policy(disabled, [SER], _live())
    step = [s for s in plan["steps"] if s["kind"] == "enable_automation"][0]
    assert step["action"] == "disable"


def test_no_devices_is_an_issue_not_a_blocker():
    plan = plan_policy(load_policy(FULL_YAML), [], _live())
    assert any(i["code"] == "no_devices" for i in plan["issues"])
    # nothing to do ≠ refusal — but extension steps may still plan globally
    assert all(b["code"] != "no_devices" for b in plan["blockers"])
