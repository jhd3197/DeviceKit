"""Policy apply as a job: refusal, fan-out, snapshots, idempotence (plan 23 phase 4).

The end-to-end tests run a real JobConsumer over the temp DB against a mutable fake fleet,
so an apply visibly *changes* the fleet and the re-plan proves convergence.
"""
import time

import pytest

from devicekit.jobs import JobConsumer
from devicekit.jobs.service import JobService
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.mixins.fleet import FleetMixin
from devicekit.mixins.fleet_policy import FleetPolicyMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.mixins.vault import VaultMixin
from devicekit.mixins.workspaces import WorkspacesMixin

POLICY_YAML = """
version: 1
target: {device: SER1}
automations:
  - {automation: cleanup, schedule: {intervalMinutes: 30}}
settings:
  system: {screen_brightness: 128}
"""


class _FakeFleet:
    """Mutable device-side state the stub ADB layer reads and writes."""

    def __init__(self, devices=("SER1",)):
        self.devices = {d: {"online": True} for d in devices}
        self.settings = {(d, "system", "screen_brightness"): "40" for d in devices}
        self.readonly = set()


class _ApplyClient(FleetPolicyMixin, AutomationMixin, FleetMixin, VaultMixin,
                   JobsMixin, WorkspacesMixin, IdentityMixin, AuthMixin):
    def __init__(self, fleet):
        self.configure_auth("", [])
        self._has_users_flag = None
        self.fleet = fleet

    def broadcast(self, event_type, data):
        pass

    def all_devices_for_query(self):
        return [{"serial": d, "device_id": d, "online": st["online"]}
                for d, st in self.fleet.devices.items()]

    def run_adb_command(self, args, device=None):
        f = self.fleet
        if args[:3] == ["shell", "settings", "get"]:
            return f.settings.get((device, args[3], args[4]), "null")
        if args[:3] == ["shell", "settings", "put"]:
            if (device, args[3], args[4]) not in f.readonly:
                f.settings[(device, args[3], args[4])] = args[5]
            return ""
        return ""


@pytest.fixture
def fleet():
    return _FakeFleet()


@pytest.fixture
def client(fresh_db, fleet):
    c = _ApplyClient(fleet)
    c.init_fleet_policy()          # registers policy.apply + policy.apply.device kinds
    c.create_automation("cleanup")
    return c


@pytest.fixture
def consumer(client):
    consumer = JobConsumer(poll_interval_seconds=0.05, max_workers=3)
    consumer.start()
    yield consumer
    consumer.stop()


def _wait(job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = JobService.get(job_id)
        if row and row["status"] in ("succeeded", "failed", "cancelled"):
            return row
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


# --------------------------------------------------------------- gates (no consumer)
def test_blockers_refuse_apply(client, fleet):
    fleet.devices["SER1"]["online"] = False
    p = client.create_fleet_policy(POLICY_YAML)
    result = client.apply_fleet_policy(p["id"])
    assert result["refused"] is True
    assert [b["code"] for b in result["plan"]["blockers"]] == ["device_offline"]
    assert client.get_fleet_policy(p["id"])["status"] == "pending"   # untouched
    assert JobService.list() == []                                   # no half-deploy job


def test_already_converged_marks_applied_without_job(client, fleet):
    fleet.settings[("SER1", "system", "screen_brightness")] = "128"
    p = client.create_fleet_policy(
        "version: 1\ntarget: {device: SER1}\n"
        "settings: {system: {screen_brightness: 128}}\n")
    result = client.apply_fleet_policy(p["id"])
    assert result == {"applied": True, "empty": True, "policy": result["policy"]}
    assert result["policy"]["status"] == "applied"
    assert result["policy"]["applied_hash"] == p["policy_hash"]
    assert JobService.list() == []


def test_stale_hash_recheck_skips(client):
    p = client.create_fleet_policy(POLICY_YAML)
    out = client._job_apply_policy({"payload": {
        "policy_id": p["id"], "policy_hash": "stale", "plan": {"steps": []}}})
    assert out == {"skipped": "policy edited since enqueue"}
    assert client.get_fleet_policy(p["id"])["status"] == "pending"


# --------------------------------------------------------------- end-to-end via consumer
def test_apply_converges_then_short_circuits(client, fleet, consumer):
    p = client.create_fleet_policy(POLICY_YAML)
    result = client.apply_fleet_policy(p["id"])
    parent = _wait(result["job"]["id"])

    assert parent["status"] == "succeeded"
    device_result = parent["result"]["devices"]["SER1"]
    assert device_result["ok"] is True
    assert [s["status"] for s in device_result["steps"]] == ["ok", "ok"]
    # Before/after snapshots captured the transition the policy governs.
    assert device_result["before"]["settings"]["system.screen_brightness"] == "40"
    assert device_result["after"]["settings"]["system.screen_brightness"] == "128"
    assert device_result["after"]["automations"]["cleanup"]["enabled"] is True

    # The fleet actually changed, the policy is applied, and the re-plan is empty.
    assert fleet.settings[("SER1", "system", "screen_brightness")] == "128"
    policy = client.get_fleet_policy(p["id"])
    assert policy["status"] == "applied" and policy["applied_hash"] == p["policy_hash"]
    assert client.plan_fleet_policy(p["id"])["empty"] is True

    # Idempotent: an unchanged hash short-circuits without enqueueing anything.
    again = client.apply_fleet_policy(p["id"])
    assert again["short_circuit"] is True
    assert len(JobService.list(kind="policy.apply")) == 1


def test_apply_fans_out_per_device_group(fresh_db, consumer=None):
    fleet = _FakeFleet(devices=("SER1", "SER2"))
    client = _ApplyClient(fleet)
    client.init_fleet_policy()
    group = client.create_device_group("kiosks", device_ids=["SER1", "SER2"])
    p = client.create_fleet_policy(
        f"version: 1\ntarget: {{group: {group['id']}}}\n"
        "settings: {system: {screen_brightness: 200}}\n"
        "overrides:\n  SER2:\n    settings: {system: {screen_brightness: 90}}\n")
    consumer = JobConsumer(poll_interval_seconds=0.05, max_workers=3)
    consumer.start()
    try:
        result = client.apply_fleet_policy(p["id"])
        parent = _wait(result["job"]["id"])
    finally:
        consumer.stop()
    assert parent["status"] == "succeeded"
    assert set(parent["result"]["devices"]) == {"SER1", "SER2"}
    # One child job per device, and the per-device override was honored.
    assert len(JobService.list(kind="policy.apply.device")) == 2
    assert fleet.settings[("SER1", "system", "screen_brightness")] == "200"
    assert fleet.settings[("SER2", "system", "screen_brightness")] == "90"
    assert client.get_fleet_policy(p["id"])["status"] == "applied"


def test_step_failure_stops_device_and_marks_error(client, fleet, consumer):
    fleet.readonly.add(("SER1", "system", "screen_brightness"))   # put silently fails
    p = client.create_fleet_policy(POLICY_YAML)
    result = client.apply_fleet_policy(p["id"])
    parent = _wait(result["job"]["id"])

    device_result = parent["result"]["devices"]["SER1"]
    assert device_result["ok"] is False
    # Stop-on-first-failure: the setting errored, the schedule step never ran.
    assert [s["status"] for s in device_result["steps"]] == ["error", "skipped"]
    assert "verification failed" in device_result["error"]
    policy = client.get_fleet_policy(p["id"])
    assert policy["status"] == "error"
    assert policy["applied_hash"] is None                          # never applied
    assert "failed" in policy["status_detail"]["summary"]
    # The skipped schedule was truly not created.
    assert client.list_schedules() == []


# --------------------------------------------------------------- step executors (direct)
def test_generate_secret_mints_stores_and_applies(client, fleet):
    vault = client.create_vault("Fleet", slug="fleet")
    outcome = client._exec_policy_step(
        {"kind": "configure_setting", "namespace": "system", "key": "lock_pin",
         "secret": True, "generate": True,
         "from_secret": {"vault": "fleet", "key": "PIN"}}, "SER1")
    assert outcome["secret"] is True
    minted = client.reveal_secret(vault["id"], "PIN")["value"]     # stored in the vault
    assert fleet.settings[("SER1", "system", "lock_pin")] == minted
    # Second run resolves the same stored secret (no re-mint).
    client._exec_policy_step(
        {"kind": "configure_setting", "namespace": "system", "key": "lock_pin",
         "secret": True, "generate": True,
         "from_secret": {"vault": "fleet", "key": "PIN"}}, "SER1")
    assert client.reveal_secret(vault["id"], "PIN")["value"] == minted


def test_provision_step_rides_appdriver(client, monkeypatch):
    import devicekit_sdk.appdriver as appdriver
    calls = {}

    def _fake_provision(slug, device_id, **kwargs):
        calls.update({"slug": slug, "device_id": device_id, **kwargs})
        return {"version_name": "12.4.0"}

    monkeypatch.setattr(appdriver, "provision", _fake_provision)
    monkeypatch.setattr(_ApplyClient, "get_extension_config_raw",
                        lambda self, slug: {"apk_b64": "QUJD", "apk_sha256": "aa",
                                            "apk_version": "12.4.0"}, raising=False)
    outcome = client._exec_policy_step(
        {"kind": "provision_app", "package": "com.expressvpn.vpn",
         "extension": "devicekit-vpn", "desired_version": "12.4.0"}, "SER1")
    assert outcome == {"package": "com.expressvpn.vpn", "version": "12.4.0"}
    assert calls["slug"] == "devicekit-vpn" and calls["device_id"] == "SER1"
    assert calls["expected_version"] == "12.4.0" and calls["apk_b64"] == "QUJD"
