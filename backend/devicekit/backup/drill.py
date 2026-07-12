"""Restore drill (plan 25 part 6) — the standout of the ServerKit backup doctrine.

Restore the latest backup into a **throwaway scratch dir + SQLite DB**, probe-verify it, and
tear it down — **never touching live**. The guards are the point:

* **free-space precheck** → a loud ``skipped_no_space`` (never a silent pass that hides a
  drill that couldn't actually run);
* **vacuous-drill guard** → a 0-file restore *fails loud* instead of earning ``drilled``;
* the scratch dir is dropped in a ``finally`` no matter what.

A drill that can't prove the backup restores must not report success — that's how a backup
stays a safety net instead of an assumption.
"""
import os
import shutil
import sqlite3
import tarfile
import tempfile

from devicekit.models.backup import (
    DRILL_PASSED, DRILL_FAILED, DRILL_SKIPPED_NO_SPACE)

# Require this multiple of the tarball size free before drilling (extract + scratch headroom).
FREE_SPACE_FACTOR = 3


def _probe_restore(scratch_dir):
    """Probe-verify a restored tree: file count + total bytes + table count.

    Returns ``(ok, detail)``. The **vacuous-drill guard** lives here: zero files (or a DB with
    zero tables / zero bytes) is a failure, never a pass.
    """
    files = []
    total_bytes = 0
    for root, _dirs, names in os.walk(scratch_dir):
        for n in names:
            p = os.path.join(root, n)
            files.append(p)
            total_bytes += os.path.getsize(p)

    detail = {"files": len(files), "bytes": total_bytes}
    if not files:
        detail["error"] = "vacuous drill: 0 files restored"
        return False, detail
    if total_bytes == 0:
        detail["error"] = "vacuous drill: 0 bytes restored"
        return False, detail

    db_path = os.path.join(scratch_dir, "devicekit.db")
    if not os.path.exists(db_path):
        detail["error"] = "restored tree has no devicekit.db"
        return False, detail
    try:
        con = sqlite3.connect(db_path)
        try:
            tables = con.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            con.close()
    except Exception as e:
        detail["error"] = f"scratch DB unusable: {e}"
        return False, detail
    detail["tables"] = tables
    if tables == 0:
        detail["error"] = "vacuous drill: restored DB has 0 tables"
        return False, detail
    return True, detail


def run_drill(tar_path, scratch_root=None, required_free_bytes=None):
    """Restore ``tar_path`` into a throwaway scratch dir and probe-verify it.

    ``required_free_bytes`` overrides the free-space threshold (used by tests); otherwise it is
    ``tarball_size * FREE_SPACE_FACTOR``. Returns ``{status, detail}`` with status one of
    ``passed`` / ``failed`` / ``skipped_no_space``.
    """
    if not os.path.exists(tar_path):
        return {"status": DRILL_FAILED, "detail": {"error": "backup tarball missing"}}

    size = os.path.getsize(tar_path)
    scratch_root = scratch_root or tempfile.gettempdir()
    need = required_free_bytes if required_free_bytes is not None else size * FREE_SPACE_FACTOR

    # Free-space precheck — a LOUD skip, never a silent pass.
    try:
        free = shutil.disk_usage(scratch_root).free
    except Exception as e:
        return {"status": DRILL_SKIPPED_NO_SPACE,
                "detail": {"error": f"cannot stat free space: {e}"}}
    if free < need:
        return {"status": DRILL_SKIPPED_NO_SPACE,
                "detail": {"free_bytes": free, "required_bytes": need,
                           "note": "insufficient free space to drill safely"}}

    scratch = tempfile.mkdtemp(prefix="dk-drill-", dir=scratch_root)
    try:
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(scratch)
        except Exception as e:
            return {"status": DRILL_FAILED, "detail": {"error": f"extract failed: {e}"}}
        ok, detail = _probe_restore(scratch)
        return {"status": DRILL_PASSED if ok else DRILL_FAILED, "detail": detail}
    finally:
        # The scratch DB is ALWAYS dropped — a drill never leaves state behind, never touches live.
        shutil.rmtree(scratch, ignore_errors=True)
