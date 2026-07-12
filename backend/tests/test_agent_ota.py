"""Plan 25 part 3 — OTA agent updates: Ed25519 signing, rollout cohort/advance policy,
signed agent-pull, crash-loop backoff, and auto-rollback."""
import io
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from devicekit.ota import signing
from devicekit.ota.rollout import (
    device_bucket, in_cohort, evaluate_rollout, normalize_config, STAGES)
from devicekit.mixins.agent_ota import AgentOtaMixin
from devicekit.mixins.agent_device import AgentDeviceMixin


# ------------------------------------------------------------------------- signing (pure)
def test_sign_verify_roundtrip():
    key = Ed25519PrivateKey.generate()
    pub = signing.public_key_hex(key)
    manifest = {"release_id": "r1", "version_code": 5, "sha256": "abc"}
    sig = signing.sign_manifest(key, manifest)
    assert signing.verify_manifest(pub, manifest, sig)


def test_verify_rejects_tampered_manifest():
    key = Ed25519PrivateKey.generate()
    pub = signing.public_key_hex(key)
    manifest = {"release_id": "r1", "version_code": 5, "sha256": "abc"}
    sig = signing.sign_manifest(key, manifest)
    tampered = dict(manifest, sha256="deadbeef")  # swapped the pinned hash
    assert not signing.verify_manifest(pub, tampered, sig)


def test_verify_ignores_signature_and_pubkey_fields():
    # A distributed manifest carries signature/public_key; they must be excluded from the
    # signed bytes or verification of the round-tripped object would fail.
    key = Ed25519PrivateKey.generate()
    pub = signing.public_key_hex(key)
    manifest = {"version_code": 1, "sha256": "x"}
    sig = signing.sign_manifest(key, manifest)
    wire = dict(manifest, signature=sig, public_key=pub)
    assert signing.verify_manifest(pub, wire, sig)


def test_verify_rejects_wrong_key():
    key = Ed25519PrivateKey.generate()
    other = signing.public_key_hex(Ed25519PrivateKey.generate())
    manifest = {"version_code": 1}
    sig = signing.sign_manifest(key, manifest)
    assert not signing.verify_manifest(other, manifest, sig)


# ------------------------------------------------------------------------- rollout (pure)
def test_device_bucket_is_deterministic_and_bounded():
    b = device_bucket("samsung_SM-S134DL")
    assert b == device_bucket("samsung_SM-S134DL")
    assert 0 <= b < 100


def test_cohort_widens_monotonically():
    cfg = {"canary_percent": 10, "staged_percent": 50}
    # a device in canary is necessarily in staged and full
    canary_dev = next(d for d in (f"d{i}" for i in range(1000))
                      if in_cohort(d, "canary", cfg))
    assert in_cohort(canary_dev, "staged", cfg)
    assert in_cohort(canary_dev, "full", cfg)


def test_full_stage_includes_everyone():
    assert in_cohort("anything", "full", {})


def test_evaluate_holds_during_dwell():
    d = evaluate_rollout("canary", stage_entered_at=100, now=100,
                         stats={"installed": 1, "failed": 0},
                         config={"dwell_seconds": 3600})
    assert d["action"] == "hold"


def test_evaluate_advances_after_dwell():
    d = evaluate_rollout("canary", stage_entered_at=0, now=10_000,
                         stats={"installed": 5, "failed": 0},
                         config={"dwell_seconds": 3600})
    assert d == {"action": "advance", "next_stage": "staged"}


def test_evaluate_completes_at_full():
    d = evaluate_rollout("full", stage_entered_at=0, now=10_000,
                         stats={"installed": 5, "failed": 0},
                         config={"dwell_seconds": 0})
    assert d["action"] == "complete"


def test_evaluate_rolls_back_on_failures_before_dwell():
    d = evaluate_rollout("canary", stage_entered_at=0, now=1,  # dwell not elapsed
                         stats={"installed": 1, "failed": 4},
                         config={"dwell_seconds": 3600, "failure_threshold": 0.34,
                                 "min_samples": 3})
    assert d["action"] == "rollback"


def test_evaluate_needs_min_samples_to_rollback():
    d = evaluate_rollout("canary", stage_entered_at=0, now=1,
                         stats={"installed": 0, "failed": 1},
                         config={"dwell_seconds": 3600, "min_samples": 3})
    assert d["action"] == "hold"  # only 1 sample — not enough to condemn the release


# ------------------------------------------------------------------------- stateful mixin
def _fake_apk(marker=b"x"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("classes.dex", marker)
    return buf.getvalue()


class _Ota(AgentOtaMixin, AgentDeviceMixin):
    def __init__(self, output_dir):
        self.output_dir = str(output_dir)
        # Ephemeral signing key so tests never touch the on-disk key file.
        self._ota_key = Ed25519PrivateKey.generate()
        self.init_agent_registry()


@pytest.fixture
def ota(fresh_db, tmp_path):
    return _Ota(tmp_path)


def _register(client, device_id, version_code):
    client.register_agent_device(
        device_id, info={"agent_version": "1.0.0", "agent_version_code": version_code},
        serial=device_id)


def test_create_release_signs_and_hashes(ota):
    rel = ota.create_agent_release(_fake_apk(), version_name="1.1.0", version_code=2)
    assert rel["sha256"] and rel["signature"]
    # The signed manifest verifies against the advertised public key.
    manifest = {"release_id": rel["id"], "version_name": "1.1.0", "version_code": 2,
                "sha256": rel["sha256"], "size_bytes": rel["size_bytes"]}
    assert signing.verify_manifest(rel["public_key"], manifest, rel["signature"])


def test_create_release_rejects_non_apk(ota):
    with pytest.raises(ValueError):
        ota.create_agent_release(b"not a zip", version_name="1.0.0", version_code=1)


def test_download_bytes_match_hash(ota):
    apk = _fake_apk(b"payload")
    rel = ota.create_agent_release(apk, version_name="1.0.0", version_code=1)
    data, name = ota.get_release_apk(rel["id"])
    import hashlib
    assert hashlib.sha256(data).hexdigest() == rel["sha256"]


def test_update_offered_to_in_cohort_device(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    ota.create_agent_rollout(rel["id"], config={"canary_percent": 100})  # everyone in canary
    out = ota.check_device_update("d1")
    assert out["update"] is True
    assert out["manifest"]["version_code"] == 5
    assert out["signature"] and out["download_path"].endswith("/apk")


def test_update_not_offered_out_of_cohort(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    ota.create_agent_rollout(rel["id"], config={"canary_percent": 0})  # nobody in canary
    assert ota.check_device_update("d1") == {"update": False}


def test_update_not_offered_when_already_current(ota):
    _register(ota, "d1", version_code=5)  # already on the release version
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    ota.create_agent_rollout(rel["id"], config={"canary_percent": 100})
    assert ota.check_device_update("d1") == {"update": False}


def test_crash_loop_backoff_stops_offering(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    rollout = ota.create_agent_rollout(rel["id"], config={"canary_percent": 100})
    assert ota.check_device_update("d1")["update"] is True
    for _ in range(3):
        ota.report_device_update("d1", rollout["id"], "failed", version_code=5, error="boom")
    # after 3 failed attempts the device is no longer offered the bad build
    assert ota.check_device_update("d1") == {"update": False}


def test_report_installed_bumps_version_and_stops_offering(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    rollout = ota.create_agent_rollout(rel["id"], config={"canary_percent": 100})
    ota.check_device_update("d1")
    ota.report_device_update("d1", rollout["id"], "installed", version_code=5)
    prog = ota.rollout_progress(rollout["id"])
    assert prog["installed"] == 1
    assert ota.check_device_update("d1") == {"update": False}


def test_advance_progresses_stage_after_dwell(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    rollout = ota.create_agent_rollout(
        rel["id"], config={"canary_percent": 100, "dwell_seconds": 0})
    summary = ota.advance_rollouts()
    assert summary["advanced"] == 1
    assert ota.get_agent_rollout(rollout["id"])["stage"] == "staged"


def test_advance_auto_rolls_back_on_failures(ota):
    _register(ota, "d1", version_code=1)
    old = ota.create_agent_release(_fake_apk(b"old"), version_name="1.0.0", version_code=1)
    new = ota.create_agent_release(_fake_apk(b"new"), version_name="2.0.0", version_code=5)
    rollout = ota.create_agent_rollout(
        new["id"], config={"canary_percent": 100, "dwell_seconds": 3600,
                           "min_samples": 1, "failure_threshold": 0.5})
    ota.check_device_update("d1")
    ota.report_device_update("d1", rollout["id"], "failed", version_code=5, error="boom")
    summary = ota.advance_rollouts()
    assert summary["rolled_back"] == 1
    assert ota.get_agent_rollout(rollout["id"])["status"] == "rolled_back"
    # a rollback rollout to the prior version was opened
    active = ota.list_agent_rollouts(status="active")
    assert any(r["release_id"] == old["id"] and r["rollback_of"] == rollout["id"]
               for r in active)


def test_manual_rollback_stops_offers(ota):
    _register(ota, "d1", version_code=1)
    rel = ota.create_agent_release(_fake_apk(), version_name="2.0.0", version_code=5)
    rollout = ota.create_agent_rollout(rel["id"], config={"canary_percent": 100})
    ota.rollback_rollout(rollout["id"], reason="operator pulled it")
    assert ota.get_agent_rollout(rollout["id"])["status"] == "rolled_back"
    # the rolled-back rollout no longer offers (no prior release exists here → no rollback rollout)
    assert ota.check_device_update("d1") == {"update": False}
