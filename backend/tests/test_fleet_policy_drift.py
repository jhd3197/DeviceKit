"""Drift detection + reconcile: edge-triggered alerts, opt-in autoApply (plan 23 phase 5)."""
import time

import pytest

from devicekit.db import session_scope
from devicekit.jobs import JobConsumer
from devicekit.jobs.models import ScheduledJob
from devicekit.jobs.service import JobService

from test_fleet_policy_apply import _ApplyClient, _FakeFleet, POLICY_YAML, _wait

BRIGHTNESS = ("SER1", "system", "screen_brightness")


class _DriftClient(_ApplyClient):
    def __init__(self, fleet):
        super().__init__(fleet)
        self.notified = []

    def notify_event(self, event_key, data=None, **kwargs):
        self.notified.append((event_key, data))


@pytest.fixture
def fleet():
    return _FakeFleet()


@pytest.fixture
def client(fresh_db, fleet):
    c = _DriftClient(fleet)
    c.init_fleet_policy()
    c.create_automation("cleanup")
    return c


def _applied_policy(client, fleet, yaml=POLICY_YAML, **create_kwargs):
    """Create a policy whose live state already matches, applied without a job."""
    fleet.settings[BRIGHTNESS] = "128"
    p = client.create_fleet_policy(yaml, **create_kwargs)
    sched = client.create_schedule(
        client.list_automations()[0]["id"], "SER1", 30, enabled=True)
    result = client.apply_fleet_policy(p["id"])
    assert result.get("empty") or result.get("short_circuit")
    return client.get_fleet_policy(p["id"]), sched


# --------------------------------------------------------------- edge transitions
def test_drift_detected_once_then_resolves(client, fleet):
    p, _ = _applied_policy(client, fleet)
    assert client.check_fleet_policy_drift(p["id"])["drifted"] is False

    fleet.settings[BRIGHTNESS] = "11"          # someone fiddles with the device
    first = client.check_fleet_policy_drift(p["id"])
    assert first["drifted"] is True and first["edge"] is True
    policy = client.get_fleet_policy(p["id"])
    assert policy["status"] == "drifted"
    assert "diverged" in policy["status_detail"]["summary"]
    assert [e for e, _ in client.notified] == ["policy.drift.detected"]

    second = client.check_fleet_policy_drift(p["id"])
    assert second["drifted"] is True and second["edge"] is False
    assert len(client.notified) == 1           # edge-triggered: no re-alert

    fleet.settings[BRIGHTNESS] = "128"         # fixed by hand
    resolved = client.check_fleet_policy_drift(p["id"])
    assert resolved["drifted"] is False and resolved["edge"] is True
    assert client.get_fleet_policy(p["id"])["status"] == "applied"
    assert [e for e, _ in client.notified] == [
        "policy.drift.detected", "policy.drift.resolved"]


def test_pending_policies_are_not_drift_checked(client):
    p = client.create_fleet_policy(POLICY_YAML)
    out = client.check_fleet_policy_drift(p["id"])
    assert out["checked"] is False
    assert client.get_fleet_policy(p["id"])["status"] == "pending"


def test_drift_sweep_job_counts(client, fleet):
    p, _ = _applied_policy(client, fleet)
    client.create_fleet_policy("version: 1\ntarget: {device: SER1}\n")  # stays pending
    fleet.settings[BRIGHTNESS] = "1"
    out = client._job_check_policy_drift({"payload": {}})
    assert out == {"checked": 1, "drifted": 1, "resolved": 0, "auto_applied": 0}
    assert client.get_fleet_policy(p["id"])["last_checked_at"] is not None


# --------------------------------------------------------------- reconcile
def test_reconcile_is_not_short_circuited_when_drifted(client, fleet):
    p, _ = _applied_policy(client, fleet)
    fleet.settings[BRIGHTNESS] = "11"
    client.check_fleet_policy_drift(p["id"])
    # Same hash as applied_hash, but drifted status means reconcile really runs.
    result = client.apply_fleet_policy(p["id"], triggered_by="reconcile")
    assert "short_circuit" not in result and result.get("job")

    consumer = JobConsumer(poll_interval_seconds=0.05, max_workers=3)
    consumer.start()
    try:
        _wait(result["job"]["id"])
    finally:
        consumer.stop()
    assert fleet.settings[BRIGHTNESS] == "128"
    assert client.get_fleet_policy(p["id"])["status"] == "applied"


# --------------------------------------------------------------- autoApply (opt-in)
def test_auto_apply_reconciles_on_the_drift_edge(client, fleet):
    p, _ = _applied_policy(
        client, fleet, yaml=POLICY_YAML.replace("version: 1", "version: 1\nautoApply: true"))
    assert p["auto_apply"] is True
    fleet.settings[BRIGHTNESS] = "11"
    out = client.check_fleet_policy_drift(p["id"])
    assert out["edge"] is True and out["auto_applied"] is True
    assert len(JobService.list(kind="policy.apply")) == 1


def test_default_stays_pending_by_default(client, fleet):
    p, _ = _applied_policy(client, fleet)          # autoApply defaults off
    fleet.settings[BRIGHTNESS] = "11"
    out = client.check_fleet_policy_drift(p["id"])
    assert out["edge"] is True and out["auto_applied"] is False
    assert JobService.list(kind="policy.apply") == []   # operator must reconcile


def test_auto_apply_never_fires_through_blockers(client, fleet):
    p, _ = _applied_policy(
        client, fleet, yaml=POLICY_YAML.replace("version: 1", "version: 1\nautoApply: true"))
    fleet.settings[BRIGHTNESS] = "11"
    fleet.devices["SER1"]["online"] = False        # drifted AND blocked
    out = client.check_fleet_policy_drift(p["id"])
    assert out["drifted"] is True and out["auto_applied"] is False
    assert JobService.list(kind="policy.apply") == []
    detail = client.get_fleet_policy(p["id"])["status_detail"]
    assert detail["blockers"]                       # refusal is visible to the operator


# --------------------------------------------------------------- scheduling
def test_drift_check_is_a_scheduled_job(client):
    with session_scope() as s:
        row = s.query(ScheduledJob).filter(
            ScheduledJob.name == "policy.drift.check").one()
        assert row.kind == "policy.drift.check"
        assert row.interval_seconds == 300 and bool(row.enabled) is True
