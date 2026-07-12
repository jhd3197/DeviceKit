"""Create a backup: consistent DB snapshot + redacted config → tarball + manifest (plan 25 p6).

The manifest.json is written **beside** the tarball, not inside it, on purpose: hash
verification must compare a tar member against a hash the corrupt tar can't have altered.
The SQLite snapshot uses the online backup API so a live, mid-write DB is captured
consistently (never a torn file copy).
"""
import os
import json
import time
import uuid
import shutil
import hashlib
import sqlite3
import tarfile
import tempfile
import platform


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_path_from_url(database_url):
    """Extract a filesystem path from a ``sqlite:///...`` URL, or None for non-SQLite."""
    if not database_url or not database_url.startswith("sqlite:///"):
        return None
    return database_url[len("sqlite:///"):]


def _snapshot_sqlite(src_path, dst_path):
    """Consistent snapshot of a live SQLite DB via the online backup API."""
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _alembic_head(db_path):
    try:
        con = sqlite3.connect(db_path)
        try:
            row = con.execute("SELECT version_num FROM alembic_version").fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except Exception:
        return None


def create_backup(database_url, backups_dir, config_snapshot=None, chain_prev=None):
    """Create a backup of the SQLite DB + a redacted config snapshot.

    Returns ``{backup_id, path, manifest_path, manifest, size_bytes}``. Raises ``ValueError``
    for a non-SQLite database (local SQLite is this plan's scope; offsite/Postgres is a future
    opt-in).
    """
    db_path = _sqlite_path_from_url(database_url)
    if not db_path or not os.path.exists(db_path):
        raise ValueError(f"backup supports a local SQLite DB only (got {database_url!r})")

    backup_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    out_dir = os.path.join(backups_dir, backup_id)
    os.makedirs(out_dir, exist_ok=True)
    staging = tempfile.mkdtemp(prefix="dk-backup-")
    try:
        # 1) consistent DB snapshot
        snap_db = os.path.join(staging, "devicekit.db")
        _snapshot_sqlite(db_path, snap_db)

        # 2) redacted config snapshot (keys + types only; never values)
        config_file = os.path.join(staging, "config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_snapshot or {}, f, sort_keys=True, indent=2)

        artifacts = []
        for name in ("devicekit.db", "config.json"):
            p = os.path.join(staging, name)
            artifacts.append({"name": name, "sha256": _sha256_file(p),
                              "size_bytes": os.path.getsize(p)})

        # 3) tarball
        tar_path = os.path.join(out_dir, "backup.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tar:
            for name in ("devicekit.db", "config.json"):
                tar.add(os.path.join(staging, name), arcname=name)

        # 4) manifest — stored SEPARATELY from the tarball
        manifest = {
            "backup_id": backup_id,
            "created_at": time.time(),
            "artifacts": artifacts,
            "tool_versions": {
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "schema": _alembic_head(snap_db),
            },
            "chain": {"prev": chain_prev},
        }
        manifest_path = os.path.join(out_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, sort_keys=True, indent=2)

        return {
            "backup_id": backup_id,
            "path": tar_path,
            "manifest_path": manifest_path,
            "manifest": manifest,
            "size_bytes": os.path.getsize(tar_path),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
