"""Plan 25 part 4 — device onboarding state machine on the job bus:
pending → validating → provisioning → ready | failed, with an ordered progress log and
policy-on-ready (plan 23)."""
import pytest

from devicekit.mixins.onboarding import OnboardingMixin
from devicekit.mixins.agent_device import AgentDeviceMixin
from devicekit.models.onboarding import (
    STATE_PENDING, STATE_VALIDATING, STATE_PROVISIONING, STATE_READY, STATE_FAILED)


class _Onboard(OnboardingMixin, AgentDeviceMixin):
    def __init__(self):
        self.enqueued = []
        self.init_agent_registry()

    def enqueue_job(self, kind, payload=None, **kw):
        self.enqueued.append((kind, payload))
        return {"id": f"job-{len(self.enqueued)}"}


@pytest.fixture
def ob(fresh_db):
    return _Onboard()


def _register(ob, device_id):
    ob.register_agent_device(device_id, info={"model": device_id}, serial=device_id)


def test_start_creates_pending_and_enqueues(ob):
    _register(ob, "d1")
    session = ob.start_onboarding("d1", serial="d1")
    assert session["state"] == STATE_PENDING
    assert ob.enqueued[0][0] == "onboarding.advance"


def test_full_lifecycle_to_ready(ob):
    _register(ob, "d1")
    s = ob.start_onboarding("d1")
    sid = s["id"]
    assert ob.advance_onboarding(sid)["state"] == STATE_VALIDATING
    assert ob.advance_onboarding(sid)["state"] == STATE_PROVISIONING
    assert ob.advance_onboarding(sid)["state"] == STATE_READY
    final = ob.get_onboarding_session(sid)
    assert final["state"] == STATE_READY
    assert [step["step"] for step in final["steps"]] == ["validate", "provision", "finalize"]
    assert all(step["status"] == "ok" for step in final["steps"])
    assert final["completed_at"] is not None


def test_validation_fails_for_unreachable_device(ob):
    # No registration for this device → validation can't pass.
    s = ob.start_onboarding("ghost")
    out = ob.advance_onboarding(s["id"])
    assert out["state"] == STATE_FAILED
    session = ob.get_onboarding_session(s["id"])
    assert session["state"] == STATE_FAILED
    assert session["steps"][0]["step"] == "validate"
    assert session["steps"][0]["status"] == "error"
    assert session["error"]


def test_start_is_idempotent_while_active(ob):
    _register(ob, "d1")
    s1 = ob.start_onboarding("d1")
    s2 = ob.start_onboarding("d1")   # still pending → same session, no duplicate
    assert s1["id"] == s2["id"]


def test_start_after_terminal_creates_new_session(ob):
    s1 = ob.start_onboarding("ghost")
    ob.advance_onboarding(s1["id"])   # fails validation → terminal
    _register(ob, "ghost")
    s2 = ob.start_onboarding("ghost")  # terminal prior → a fresh session
    assert s2["id"] != s1["id"]
    assert s2["state"] == STATE_PENDING


def test_restart_resets_to_pending(ob):
    s = ob.start_onboarding("ghost")
    ob.advance_onboarding(s["id"])   # failed
    restarted = ob.restart_onboarding(s["id"])
    assert restarted["state"] == STATE_PENDING
    assert restarted["steps"] == []
    assert restarted["error"] is None


def test_advance_terminal_is_noop(ob):
    _register(ob, "d1")
    s = ob.start_onboarding("d1")
    for _ in range(3):
        ob.advance_onboarding(s["id"])
    out = ob.advance_onboarding(s["id"])   # already ready
    assert out["done"] is True
    assert out["state"] == STATE_READY


# --- provisioning applies a matching fleet policy (plan 23 tie-in) --------------------
class _OnboardWithPolicy(_Onboard):
    def __init__(self, targets):
        super().__init__()
        self._targets = targets   # device_id -> bool (does the policy target it)
        self.applied = []

    def list_fleet_policies(self):
        return [{"id": "p1", "name": "group-policy", "target_kind": "group",
                 "target_value": "g1"}]

    def _resolve_policy_devices(self, kind, value):
        return [d for d, hit in self._targets.items() if hit], {}

    def apply_fleet_policy(self, policy_id, triggered_by=None):
        self.applied.append((policy_id, triggered_by))
        return {"job": {"id": "j1"}}


def test_provision_applies_matching_policy(fresh_db):
    ob = _OnboardWithPolicy({"d1": True})
    ob.register_agent_device("d1", info={"model": "d1"}, serial="d1")
    s = ob.start_onboarding("d1")
    ob.advance_onboarding(s["id"])   # validating
    out = ob.advance_onboarding(s["id"])   # provisioning — should apply p1
    assert out["state"] == STATE_PROVISIONING
    assert ob.applied == [("p1", "onboarding")]
    session = ob.get_onboarding_session(s["id"])
    prov = next(st for st in session["steps"] if st["step"] == "provision")
    assert prov["detail"]["applied"][0]["policy_id"] == "p1"


def test_provision_skips_non_targeting_policy(fresh_db):
    ob = _OnboardWithPolicy({"d1": False})
    ob.register_agent_device("d1", info={"model": "d1"}, serial="d1")
    s = ob.start_onboarding("d1")
    ob.advance_onboarding(s["id"])
    ob.advance_onboarding(s["id"])
    assert ob.applied == []   # policy didn't target d1
