"""BackupMixin — backup + restore-drill of DeviceKit's own state (plan 25 part 6).

Ties the pure services together into the Client: create a backup (auto-running the
``listed`` + ``hashed`` verify ladder), persist a ``Backup`` row, and — on a schedule — run a
**restore drill** into a throwaway scratch DB. ``restore_confidence`` is surfaced for a
plan-24 doctor check with **edge-triggered** alerts (one alert when a drill starts failing,
one when it recovers — never a stream of duplicates).
"""
import os
import time
import shutil
import logging

from devicekit.db import session_scope
from devicekit.models import Backup
from devicekit.models.backup import (
    VERIFY_DRILLED, DRILL_PASSED, DRILL_FAILED, DRILL_SKIPPED_NO_SPACE)
from devicekit.backup import service as backup_service
from devicekit.backup import verify as backup_verify
from devicekit.backup import drill as backup_drill
from devicekit.scrub import types_only

logger = logging.getLogger(__name__)

BACKUP_CREATE_KIND = "backup.create"
BACKUP_DRILL_KIND = "backup.drill"


class BackupMixin:
    """Create + verify + restore-drill DeviceKit's own state."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_backup(self):
        if hasattr(self, "register_job_kind"):
            self.register_job_kind(BACKUP_CREATE_KIND, self._job_create_backup)
            self.register_job_kind(BACKUP_DRILL_KIND, self._job_run_drill)
        if hasattr(self, "ensure_scheduled_job"):
            try:
                from config import BACKUP_DRILL_INTERVAL
            except Exception:
                BACKUP_DRILL_INTERVAL = 86400
            self.ensure_scheduled_job(
                BACKUP_DRILL_KIND, BACKUP_DRILL_KIND,
                interval_seconds=BACKUP_DRILL_INTERVAL, startup_delay_seconds=120,
                owner_type="system", owner_id="core")
        if hasattr(self, "register_notification_event"):
            for key, title, sev in (
                ("backup.created", "Backup created", "info"),
                ("backup.drill.failed", "Restore drill failed", "error"),
                ("backup.drill.recovered", "Restore drill recovered", "info"),
            ):
                try:
                    self.register_notification_event(key, title, severity=sev, category="system")
                except Exception as e:
                    logger.warning(f"Backup event {key} not registered: {e}")

    def _backups_dir(self):
        d = os.path.join(getattr(self, "output_dir", "output"), "backups")
        os.makedirs(d, exist_ok=True)
        return d

    def _database_url(self):
        try:
            from config import DEVICEKIT_DATABASE_URL
            return DEVICEKIT_DATABASE_URL
        except Exception:
            from devicekit.db import get_engine
            return str(get_engine().url)

    def _config_snapshot(self):
        """Keys + types only of the config module — never values (scrub-first)."""
        try:
            import config as _cfg
            public = {k: getattr(_cfg, k) for k in dir(_cfg)
                      if k.isupper() and not k.startswith("_")}
            return types_only(public)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Create (auto-verify ladder)
    # ------------------------------------------------------------------
    def create_backup(self):
        """Create a backup and immediately run the ``listed`` + ``hashed`` verify ladder."""
        prev = None
        existing = self.list_backups(limit=1)
        if existing:
            prev = existing[0]["id"]
        result = backup_service.create_backup(
            self._database_url(), self._backups_dir(),
            config_snapshot=self._config_snapshot(), chain_prev=prev)

        ladder = backup_verify.verify_backup(result["path"], result["manifest_path"])
        now = time.time()
        with session_scope() as s:
            row = Backup(
                id=result["backup_id"], created_at=now, path=result["path"],
                manifest_path=result["manifest_path"], manifest=result["manifest"],
                size_bytes=result["size_bytes"], verify_level=ladder["level"],
                verify_detail=ladder["detail"], chain_prev=prev)
            s.add(row)
            s.flush()
            out = row.to_dict()
        self._broadcast_backup("created", out)
        self._notify_backup("backup.created", {"backup_id": out["id"],
                                               "verify_level": out["verify_level"]})
        self._prune_backups()
        return out

    def verify_backup(self, backup_id):
        """Re-run the verify ladder for a stored backup."""
        b = self.get_backup(backup_id)
        if not b:
            return None
        ladder = backup_verify.verify_backup(b["path"], b["manifest_path"])
        with session_scope() as s:
            row = s.get(Backup, backup_id)
            if row:
                # Don't downgrade a `drilled` row below its drill result on a re-verify.
                if row.verify_level != VERIFY_DRILLED:
                    row.verify_level = ladder["level"]
                row.verify_detail = ladder["detail"]
        return ladder

    # ------------------------------------------------------------------
    # Restore drill + restore_confidence (edge-triggered)
    # ------------------------------------------------------------------
    def run_restore_drill(self, backup_id=None):
        """Restore the latest (or a named) backup into a scratch DB, probe-verify, tear down.

        Edge-triggered: transitions to ``failed`` fire ``backup.drill.failed`` once, and a
        recovery fires ``backup.drill.recovered`` once — no duplicate spam while a condition
        persists.
        """
        b = self.get_backup(backup_id) if backup_id else (self.list_backups(limit=1) or [None])[0]
        if not b:
            return {"status": "no_backup", "detail": {"note": "no backups exist to drill"}}

        # Edge detection compares against the current global drill health *before* this run
        # writes its result (the row's own prior drill_status is included, so repeatedly
        # drilling the same backup doesn't re-alert).
        prev_status = self._latest_drill_status()
        result = backup_drill.run_drill(b["path"], scratch_root=self._backups_dir())
        status = result["status"]
        with session_scope() as s:
            row = s.get(Backup, b["id"])
            if row:
                row.drill_status = status
                row.drill_detail = result["detail"]
                row.drilled_at = time.time()
                if status == DRILL_PASSED:
                    row.verify_level = VERIFY_DRILLED
                out = row.to_dict()
            else:
                out = {"id": b["id"], "drill_status": status, "drill_detail": result["detail"]}
        self._broadcast_backup("drilled", out)

        # Edge-triggered alerts: only fire on a status transition.
        self._drill_edge_alert(prev_status, status, b["id"])
        return {"backup_id": b["id"], "status": status, "detail": result["detail"]}

    def _drill_edge_alert(self, prev_status, status, backup_id):
        failed_now = status in (DRILL_FAILED, DRILL_SKIPPED_NO_SPACE)
        failed_before = prev_status in (DRILL_FAILED, DRILL_SKIPPED_NO_SPACE)
        if failed_now and not failed_before:
            self._notify_backup("backup.drill.failed",
                                {"backup_id": backup_id, "status": status})
        elif (not failed_now) and failed_before and status == DRILL_PASSED:
            self._notify_backup("backup.drill.recovered", {"backup_id": backup_id})

    def _latest_drill_status(self):
        """The most recent drill outcome across all backups (for edge detection)."""
        with session_scope() as s:
            row = (s.query(Backup).filter(Backup.drill_status.isnot(None))
                   .order_by(Backup.drilled_at.desc()).first())
            return row.drill_status if row else None

    def restore_confidence(self):
        """The plan-24 doctor check payload: can we actually restore?

        ``status`` mirrors the doctor check contract (``ok`` / ``warn`` / ``fail``) so a doctor
        can adopt it verbatim when plan 24 lands.
        """
        latest_drilled = None
        with session_scope() as s:
            row = (s.query(Backup).filter(Backup.drill_status.isnot(None))
                   .order_by(Backup.drilled_at.desc()).first())
            if row:
                latest_drilled = row.to_dict()
        total = len(self.list_backups())
        if latest_drilled is None:
            level = "warn" if total else "fail"
            return {"key": "restore_confidence", "status": level,
                    "detail": "no restore drill has run yet" if total else "no backups exist",
                    "repairable": True, "repair_ref": BACKUP_DRILL_KIND}
        status = latest_drilled["drill_status"]
        if status == DRILL_PASSED:
            level, detail = "ok", "latest restore drill passed"
        elif status == DRILL_SKIPPED_NO_SPACE:
            level, detail = "warn", "restore drill skipped — insufficient free space"
        else:
            level, detail = "fail", f"latest restore drill: {status}"
        return {"key": "restore_confidence", "status": level, "detail": detail,
                "drilled_at": latest_drilled["drilled_at"],
                "backup_id": latest_drilled["id"],
                "repairable": True, "repair_ref": BACKUP_DRILL_KIND}

    # ------------------------------------------------------------------
    # Reads + retention
    # ------------------------------------------------------------------
    def list_backups(self, limit=50):
        with session_scope() as s:
            rows = (s.query(Backup).order_by(Backup.created_at.desc()).limit(limit).all())
            return [r.to_dict() for r in rows]

    def get_backup(self, backup_id):
        with session_scope() as s:
            r = s.get(Backup, backup_id)
            return r.to_dict() if r else None

    def delete_backup(self, backup_id):
        with session_scope() as s:
            r = s.get(Backup, backup_id)
            if not r:
                return False
            out = r.to_dict()
            s.delete(r)
        self._remove_backup_files(out)
        self._broadcast_backup("deleted", out)
        return True

    def _prune_backups(self):
        try:
            from config import BACKUP_RETENTION
        except Exception:
            BACKUP_RETENTION = 7
        backups = self.list_backups(limit=1000)
        for old in backups[BACKUP_RETENTION:]:
            self.delete_backup(old["id"])

    def _remove_backup_files(self, backup_dict):
        try:
            d = os.path.dirname(backup_dict.get("path") or "")
            if d and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Could not remove backup files for {backup_dict.get('id')}: {e}")

    # ------------------------------------------------------------------
    # Job handlers
    # ------------------------------------------------------------------
    def _job_create_backup(self, job):
        out = self.create_backup()
        return {"backup_id": out["id"], "verify_level": out["verify_level"]}

    def _job_run_drill(self, job):
        return self.run_restore_drill()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _broadcast_backup(self, event, backup_dict):
        try:
            self.broadcast("backup", {"event": event, "backup": {
                k: v for k, v in backup_dict.items() if k != "manifest"}})
        except Exception:
            pass

    def _notify_backup(self, event_key, data):
        if not hasattr(self, "notify_event"):
            return
        try:
            self.notify_event(event_key, data=data, subject_type="backup")
        except Exception:
            pass
