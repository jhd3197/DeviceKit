"""Plan 07 phase 2 — HMAC agent auth: signature verification, timestamp window, nonce
replay guard (signature checked before the nonce is consumed), rate limiting, and
zero-downtime key rotation."""
import time

from devicekit.mixins.agent_device import AgentDeviceMixin


class _Agent(AgentDeviceMixin):
    def __init__(self):
        self.init_agent_registry()

    def broadcast(self, *a, **k):
        pass

    def notify_event(self, *a, **k):
        pass


def _enroll(c, device_id="dev1"):
    c.register_agent_device(device_id, info={"model": "X"})
    return c.issue_agent_secret(device_id)


def _sign(c, secret, device_id, ts, nonce):
    return c.compute_agent_signature(secret, device_id, ts, nonce)


def test_valid_signature_accepted(fresh_db):
    c = _Agent()
    secret = _enroll(c)
    ts = str(time.time())
    sig = _sign(c, secret, "dev1", ts, "n1")
    ok, err = c.verify_agent_request("dev1", ts, "n1", sig, ip="1.1.1.1")
    assert ok is True and err is None


def test_bad_signature_rejected(fresh_db):
    c = _Agent()
    _enroll(c)
    ts = str(time.time())
    ok, err = c.verify_agent_request("dev1", ts, "n1", "deadbeef", ip="1.1.1.1")
    assert ok is False and err == "bad signature"


def test_stale_timestamp_rejected(fresh_db):
    c = _Agent()
    secret = _enroll(c)
    ts = str(time.time() - 5000)
    sig = _sign(c, secret, "dev1", ts, "n1")
    ok, err = c.verify_agent_request("dev1", ts, "n1", sig, ip="1.1.1.1", window=60)
    assert ok is False and err == "timestamp outside window"


def test_nonce_replay_rejected(fresh_db):
    c = _Agent()
    secret = _enroll(c)
    ts = str(time.time())
    sig = _sign(c, secret, "dev1", ts, "n1")
    ok1, _ = c.verify_agent_request("dev1", ts, "n1", sig, ip="1.1.1.1")
    ok2, err2 = c.verify_agent_request("dev1", ts, "n1", sig, ip="1.1.1.1")
    assert ok1 is True
    assert ok2 is False and err2 == "nonce replay"


def test_signature_checked_before_nonce_consumed(fresh_db):
    """A forged request must NOT burn a legitimate nonce: after a bad-signature attempt
    reusing a nonce, the genuine signed request with that nonce still succeeds."""
    c = _Agent()
    secret = _enroll(c)
    ts = str(time.time())
    good_sig = _sign(c, secret, "dev1", ts, "shared-nonce")
    # Attacker replays the nonce with a bad signature first.
    bad_ok, _ = c.verify_agent_request("dev1", ts, "shared-nonce", "bad", ip="9.9.9.9")
    assert bad_ok is False
    # Genuine request with the same nonce still works — the nonce wasn't consumed.
    good_ok, _ = c.verify_agent_request("dev1", ts, "shared-nonce", good_sig, ip="1.1.1.1")
    assert good_ok is True


def test_rate_limit_after_many_failures(fresh_db):
    c = _Agent()
    _enroll(c)
    ts = str(time.time())
    for _ in range(20):
        c.verify_agent_request("dev1", ts, "n", "bad", ip="7.7.7.7")
    ok, err = c.verify_agent_request("dev1", ts, "n", "bad", ip="7.7.7.7")
    assert ok is False and err == "rate limited"


def test_unenrolled_device_has_no_secret(fresh_db):
    c = _Agent()
    c.register_agent_device("dev1", info={"model": "X"})  # no secret issued
    ts = str(time.time())
    ok, err = c.verify_agent_request("dev1", ts, "n1", "whatever", ip="1.1.1.1")
    assert ok is False  # nothing to verify against


def test_key_rotation_accepts_both_secrets(fresh_db):
    c = _Agent()
    old = _enroll(c)
    new = c.start_key_rotation("dev1")
    ts = str(time.time())
    # Old secret still valid during rotation
    ok_old, _ = c.verify_agent_request("dev1", ts, "old-n", _sign(c, old, "dev1", ts, "old-n"), ip="1.1.1.1")
    # New secret already valid
    ok_new, _ = c.verify_agent_request("dev1", ts, "new-n", _sign(c, new, "dev1", ts, "new-n"), ip="1.1.1.1")
    assert ok_old and ok_new
    # After completing rotation, only the new secret works
    assert c.complete_key_rotation("dev1") is True
    ts2 = str(time.time())
    ok_old2, _ = c.verify_agent_request("dev1", ts2, "o2", _sign(c, old, "dev1", ts2, "o2"), ip="1.1.1.1")
    ok_new2, _ = c.verify_agent_request("dev1", ts2, "n2", _sign(c, new, "dev1", ts2, "n2"), ip="1.1.1.1")
    assert ok_old2 is False and ok_new2 is True
