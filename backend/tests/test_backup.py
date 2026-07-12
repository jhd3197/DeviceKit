"""Plan 25 part 6 — backup/DR: tarball + separately-stored manifest, verify ladder (hash vs
stored manifest), restore drill with its three hard guards, and scrub-first redaction."""
import os
import gzip
import json
import shutil
import tarfile

import pytest

from devicekit import db
from devicekit.backup import service as backup_service
from devicekit.backup import verify as backup_verify
from devicekit.backup import drill as backup_drill
from devicekit.models.backup import (
    VERIFY_HASHED, VERIFY_LISTED, DRILL_PASSED, DRILL_FAILED, DRILL_SKIPPED_NO_SPACE)
from devicekit.mixins.backup import BackupMixin
from devicekit.scrub import scrub, types_only


# --------------------------------------------------------------------------- scrub
def test_scrub_redacts_jwt_bearer_and_secrets():
    text = ("Authorization: Bearer eyJabc123.defG456.hijK789\n"
            "password=hunter2 and api_key: sk-livesecret\n"
            "normal line stays")
    out = scrub(text)
    assert "eyJabc123" not in out
    assert "hunter2" not in out
    assert "sk-livesecret" not in out
    assert "normal line stays" in out


def test_types_only_drops_values():
    out = types_only({"API_KEY": "secret", "PORT": 7317, "FLAG": True})
    assert out == {"API_KEY": "str", "PORT": "int", "FLAG": "bool"}
    assert "secret" not in json.dumps(out)


# ------------------------------------------------------------------- create + verify ladder
@pytest.fixture
def sqlite_url(fresh_db):
    # fresh_db yields a sqlite:///... URL for a real, migrated on-disk DB.
    return fresh_db


def test_create_backup_writes_tar_and_separate_manifest(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    assert os.path.exists(out["path"])           # tarball
    assert os.path.exists(out["manifest_path"])  # manifest.json BESIDE the tar, not inside it
    with tarfile.open(out["path"], "r:gz") as tar:
        names = tar.getnames()
    assert "manifest.json" not in names          # crucially: not in the tar
    assert set(names) == {"devicekit.db", "config.json"}
    tv = out["manifest"]["tool_versions"]
    assert tv["python"] and tv["sqlite"]         # tool versions captured
    assert "schema" in tv                        # alembic head recorded (may be None in-harness)


def test_verify_ladder_reaches_hashed(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    ladder = backup_verify.verify_backup(out["path"], out["manifest_path"])
    assert ladder["level"] == VERIFY_HASHED
    assert ladder["detail"]["listed"] and ladder["detail"]["hashed"]


def test_verify_detects_corruption_against_stored_manifest(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    # Corrupt the tarball AFTER the manifest was stored separately: the stored manifest still
    # holds the original hashes, so verify must catch the mismatch (this is the whole point).
    with open(out["path"], "r+b") as f:
        f.seek(0)
        original = f.read()
    # Rebuild a tar with a tampered devicekit.db but keep the old manifest.json on disk.
    import io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"tampered database bytes"
        info = tarfile.TarInfo("devicekit.db")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        cfg = b"{}"
        ci = tarfile.TarInfo("config.json")
        ci.size = len(cfg)
        tar.addfile(ci, io.BytesIO(cfg))
    with open(out["path"], "wb") as f:
        f.write(buf.getvalue())
    ladder = backup_verify.verify_backup(out["path"], out["manifest_path"])
    assert ladder["level"] == VERIFY_LISTED          # listable, but hash mismatch
    assert ladder["detail"]["mismatches"]


def test_unlistable_tar_is_level_none(tmp_path):
    bad = tmp_path / "backup.tar.gz"
    bad.write_bytes(b"not a tarball")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    ladder = backup_verify.verify_backup(str(bad), str(manifest))
    assert ladder["level"] == "none"


# ----------------------------------------------------------------------- restore drill
def test_drill_passes_on_a_good_backup(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    result = backup_drill.run_drill(out["path"], scratch_root=str(tmp_path))
    assert result["status"] == DRILL_PASSED
    assert result["detail"]["tables"] > 0
    assert result["detail"]["files"] >= 2


def test_drill_free_space_precheck_is_a_loud_skip(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    # Demand an absurd amount of free space → must SKIP loudly, never silently pass.
    result = backup_drill.run_drill(
        out["path"], scratch_root=str(tmp_path), required_free_bytes=10 ** 18)
    assert result["status"] == DRILL_SKIPPED_NO_SPACE
    assert "required_bytes" in result["detail"]


def test_drill_vacuous_guard_fails_on_empty_restore(tmp_path):
    # A tarball with no files at all → the vacuous-drill guard must FAIL, not earn 'passed'.
    empty_tar = tmp_path / "backup.tar.gz"
    with tarfile.open(empty_tar, "w:gz"):
        pass
    result = backup_drill.run_drill(str(empty_tar), scratch_root=str(tmp_path))
    assert result["status"] == DRILL_FAILED
    assert "vacuous" in result["detail"]["error"]


def test_drill_scratch_is_always_cleaned_up(sqlite_url, tmp_path):
    out = backup_service.create_backup(sqlite_url, str(tmp_path / "backups"))
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    backup_drill.run_drill(out["path"], scratch_root=str(scratch_root))
    # The finally-block rmtree leaves no dk-drill-* scratch dirs behind.
    leftovers = [n for n in os.listdir(scratch_root) if n.startswith("dk-drill-")]
    assert leftovers == []


# ----------------------------------------------------------------- mixin + edge alerts
class _Backup(BackupMixin):
    def __init__(self, output_dir):
        self.output_dir = str(output_dir)
        self.notified = []

    def notify_event(self, event_key, data=None, **kw):
        self.notified.append((event_key, data))


def test_create_persists_and_autoverifies(sqlite_url, tmp_path):
    c = _Backup(tmp_path / "out")
    b = c.create_backup()
    assert b["verify_level"] == VERIFY_HASHED
    assert len(c.list_backups()) == 1
    assert any(k == "backup.created" for k, _ in c.notified)


def test_restore_confidence_reflects_drill(sqlite_url, tmp_path):
    c = _Backup(tmp_path / "out")
    c.create_backup()
    assert c.restore_confidence()["status"] == "warn"   # no drill yet
    c.run_restore_drill()
    assert c.restore_confidence()["status"] == "ok"     # drill passed


def test_drill_edge_alert_fires_once(sqlite_url, tmp_path, monkeypatch):
    c = _Backup(tmp_path / "out")
    c.create_backup()
    # Force the drill to fail, twice — the failure alert must fire only on the edge.
    monkeypatch.setattr(backup_drill, "run_drill",
                        lambda *a, **k: {"status": DRILL_FAILED, "detail": {"error": "x"}})
    c.run_restore_drill()
    c.run_restore_drill()
    failed = [1 for k, _ in c.notified if k == "backup.drill.failed"]
    assert len(failed) == 1
