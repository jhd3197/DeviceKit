"""Plan 07 phase 3 — enroll → claim → poll pairing flow."""
import time

import pytest

from devicekit.mixins.agent_device import AgentDeviceMixin
from devicekit.mixins.pairing import PairingMixin


class _Agent(PairingMixin, AgentDeviceMixin):
    def __init__(self):
        self.init_agent_registry()

    def broadcast(self, *a, **k):
        pass

    def notify_event(self, *a, **k):
        pass


INFO = {"model": "A03s", "manufacturer": "samsung", "serial": "R9T",
        "capabilities": {"screen_record": True}}


def test_enroll_returns_code(fresh_db):
    c = _Agent()
    r = c.enroll_agent(INFO, serial="R9T", ip="1.1.1.1")
    assert len(r["code"]) == 6
    assert r["device_id"] == "samsung_A03s"
    assert r["pairing_id"]
    # visible to the dashboard
    pending = c.list_pending_agents()
    assert len(pending) == 1


def test_claim_mints_secret_and_enrolls(fresh_db):
    c = _Agent()
    r = c.enroll_agent(INFO)
    # Before claim, poll says not claimed.
    assert c.poll_enrollment(r["pairing_id"])["claimed"] is False

    res = c.claim_pending_agent(r["code"])
    assert res["device_id"] == "samsung_A03s"
    # Device now has a secret and capabilities were carried over.
    creds = c.get_agent_secret("samsung_A03s")
    assert creds and creds["secret"]
    assert c.get_agent_capabilities("samsung_A03s") == {"screen_record": True}

    # Agent's next poll receives the secret exactly once.
    p = c.poll_enrollment(r["pairing_id"])
    assert p["claimed"] is True
    assert p["secret"] == creds["secret"]
    # Row deleted — a second poll no longer returns the secret.
    p2 = c.poll_enrollment(r["pairing_id"])
    assert p2.get("expired") is True


def test_claim_is_case_insensitive(fresh_db):
    c = _Agent()
    r = c.enroll_agent(INFO)
    res = c.claim_pending_agent(r["code"].lower())
    assert res["enrolled"] is True


def test_unknown_code_rejected(fresh_db):
    c = _Agent()
    with pytest.raises(ValueError):
        c.claim_pending_agent("ZZZZZZ")


def test_expired_code_rejected(fresh_db):
    c = _Agent()
    r = c.enroll_agent(INFO)
    # Force-expire the pending row.
    from devicekit.db import session_scope
    from devicekit.models import PendingAgent
    with session_scope() as s:
        row = s.get(PendingAgent, r["pairing_id"])
        row.expires_at = time.time() - 1
    with pytest.raises(ValueError):
        c.claim_pending_agent(r["code"])


def test_passphrase_required_when_api_key_set(fresh_db, monkeypatch):
    c = _Agent()
    r = c.enroll_agent(INFO)
    import config
    monkeypatch.setattr(config, "API_KEY", "s3cret", raising=False)
    with pytest.raises(ValueError):
        c.claim_pending_agent(r["code"], passphrase="wrong")
    # Correct passphrase works.
    res = c.claim_pending_agent(r["code"], passphrase="s3cret")
    assert res["enrolled"] is True
