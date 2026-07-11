"""Visual baselines, debug-bundle metadata, and stream-session metadata survive a restart."""
import os
import io
import zipfile
import time

from devicekit.mixins.visual_regression import VisualRegressionMixin
from devicekit.mixins.debug_bundle import DebugBundleMixin
from devicekit.mixins.streaming import StreamingMixin
from devicekit.db import session_scope
from devicekit.models import DebugBundle


class _VR(VisualRegressionMixin):
    pass


class _Bundle(DebugBundleMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir


class _Stream(StreamingMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir


# ── Visual baselines ────────────────────────────────────────────

def test_baselines_survive_restart(fresh_db, restart):
    vr = _VR()
    img = b"\xff\xd8\xff" + b"baselinebytes" * 10
    meta = vr.create_baseline("auto-1", 0, img, device_model="Pixel", resolution="1080x1920")
    bid = meta["id"]
    assert "image_b64" not in meta  # create returns metadata only
    assert meta["image_size"] == len(img)

    restart(fresh_db)

    vr2 = _VR()
    full = vr2.get_baseline(bid)
    assert full is not None and full["image_b64"]  # get includes image
    assert vr2.get_baseline_image(bid) == img
    assert len(vr2.list_baselines("auto-1")) == 1

    found = vr2.find_baseline("auto-1", 0, device_model="Pixel", resolution="1080x1920")
    assert found["id"] == bid

    updated = vr2.update_baseline(bid, mask_regions=[{"x": 1, "y": 2, "w": 3, "h": 4}])
    assert updated["mask_regions"][0]["w"] == 3
    assert vr2.delete_baseline(bid) is True
    assert vr2.get_baseline(bid) is None


# ── Debug bundles ───────────────────────────────────────────────

def _seed_bundle(bundle, bundle_id, created_at=None):
    """Persist a bundle row + on-disk zip without a real device."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("state.json", '{"trigger":"test"}')
    zip_bytes = zip_buf.getvalue()
    zip_path = bundle._bundle_zip_path(bundle_id)
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)
    with session_scope() as s:
        s.add(DebugBundle(
            id=bundle_id, device_id="serialA", trigger="automation_failure",
            context={"error": "boom"}, files=["state.json"], size_bytes=len(zip_bytes),
            created_at=created_at or time.time(), generation_ms=5, ai_analysis=None,
            zip_path=zip_path,
        ))
    return zip_bytes


def test_debug_bundles_survive_restart(fresh_db, restart, tmp_path):
    out = str(tmp_path / "out")
    bundle = _Bundle(out)
    zip_bytes = _seed_bundle(bundle, "bundle-1")

    restart(fresh_db)

    b2 = _Bundle(out)
    meta = b2.get_debug_bundle("bundle-1")
    assert meta["trigger"] == "automation_failure"
    assert meta["context"]["error"] == "boom"
    assert b2.get_bundle_zip("bundle-1") == zip_bytes
    assert len(b2.list_debug_bundles(device_id="serialA")) == 1
    assert len(b2.list_debug_bundles(trigger="manual")) == 0

    # share link references a persisted bundle
    link = b2.generate_share_link("bundle-1")
    assert link["bundle_id"] == "bundle-1"
    data, err = b2.get_bundle_by_share_token(link["token"])
    assert err is None and data == zip_bytes

    assert b2.delete_debug_bundle("bundle-1") is True
    assert b2.get_debug_bundle("bundle-1") is None
    assert not os.path.exists(bundle._bundle_zip_path("bundle-1"))


def test_bundle_retention_cleanup(fresh_db, tmp_path):
    bundle = _Bundle(str(tmp_path / "out"))
    _seed_bundle(bundle, "old", created_at=time.time() - 40 * 86400)
    _seed_bundle(bundle, "new", created_at=time.time())
    removed = bundle.cleanup_old_bundles(max_age_days=30)
    assert removed == 1
    assert bundle.get_debug_bundle("old") is None
    assert bundle.get_debug_bundle("new") is not None


# ── Stream sessions ─────────────────────────────────────────────

def test_stream_sessions_survive_restart(fresh_db, restart, tmp_path):
    stream = _Stream(str(tmp_path / "out"))
    frames_dir = os.path.join(stream._recordings_dir(), "sess-1")
    os.makedirs(frames_dir, exist_ok=True)
    with open(os.path.join(frames_dir, "frame_000000.jpg"), "wb") as f:
        f.write(b"jpegframe")

    session = {
        "id": "sess-1", "device_id": "serialA", "fps": 10, "quality": 50,
        "started_at": 100.0, "stopped_at": 110.0, "frame_count": 1,
        "events": [{"type": "tap", "x": 5}], "frames_dir": frames_dir, "active": False,
    }
    stream._persist_session(session)

    restart(fresh_db)

    s2 = _Stream(str(tmp_path / "out"))
    meta = s2.get_recording_metadata("sess-1")
    assert meta is not None
    assert meta["frame_count"] == 1
    assert meta["duration_ms"] == 10000
    assert meta["events"][0]["type"] == "tap"

    sessions = s2.get_recording_sessions("serialA")
    assert len(sessions) == 1 and sessions[0]["session_id"] == "sess-1"

    assert s2.get_recording_frame("sess-1", 0) == b"jpegframe"
    assert s2.get_recording_frame("sess-1", 99) is None
