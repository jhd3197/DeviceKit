"""The single periodic ticker that replaces the per-domain scheduler threads (port of
ServerKit's ``jobs/scheduler.py``).

It wakes on a short interval, finds due ``ScheduledJob`` rows, and enqueues a Job for each
(advancing ``next_run_at``). All cadence lives in the DB, so adding or disabling a periodic
task is a row change, not a new daemon thread. ``session_scope`` is plain SQLAlchemy — no
Flask app context needed.
"""
import logging
import threading
import time

from devicekit.db import session_scope
from devicekit.jobs.models import ScheduledJob
from devicekit.jobs.service import ScheduledJobService

logger = logging.getLogger(__name__)


class JobScheduler:
    def __init__(self, tick_seconds=15):
        self.running = False
        self.tick_seconds = tick_seconds
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="job-scheduler")
        self._thread.start()
        logger.info("Job scheduler started")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self.tick()
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Job scheduler error: {e}")
            time.sleep(self.tick_seconds)

    def tick(self):
        """Enqueue all due schedules. Returns the number fired. Test-callable."""
        fired = 0
        for scheduled in ScheduledJobService.due():
            try:
                ScheduledJobService.fire(scheduled["id"])
                fired += 1
            except Exception as e:
                logger.error(f"Failed to fire scheduled job {scheduled.get('name')}: {e}")
                # Advance anyway so a poison schedule can't hot-loop the ticker.
                try:
                    with session_scope() as s:
                        row = s.get(ScheduledJob, scheduled["id"])
                        if row:
                            row.next_run_at = row.compute_next_run()
                except Exception:
                    pass
        return fired
