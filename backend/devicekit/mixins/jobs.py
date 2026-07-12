"""JobsMixin — the Client's façade over the unified job system (plan 05).

Owns the lifecycle (register core job kinds, start the consumer + scheduler daemons at
server boot, reconcile interrupted work) and the thin methods the ``jobs`` blueprint and the
extension SDK call. Handlers for domain kinds live with their domain
(``automation.run`` / ``automation.schedule.tick`` in ``AutomationMixin``); this mixin
registers whichever exist on the composite and owns the generic retention prunes.

Composed in ``client.py`` after the data-owning mixins and before ``EventsMixin`` is
irrelevant to ordering, but ``init_jobs`` must run after ``init_persistence`` (it writes the
default ``ScheduledJob`` rows). The consumer/scheduler threads are started only from
``build_app`` (server boot) so imports and the test-suite never spawn daemons.
"""
import logging
import os

from devicekit.jobs import registry, JobConsumer, JobScheduler
from devicekit.jobs.service import JobService, ScheduledJobService

logger = logging.getLogger(__name__)

# Bounded automation parallelism — long device runs execute on worker threads so a single
# run can't stall schedule ticks or other jobs. Per-device serialization is separate (the
# automation handler takes a per-device lock).
JOB_WORKERS = int(os.environ.get("DEVICEKIT_JOB_WORKERS", "4"))


class JobsMixin:
    _job_consumer = None
    _job_scheduler = None
    _jobs_ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_jobs(self):
        """Register core job kinds and ensure the default system schedules exist. Idempotent;
        does NOT start any thread (that happens at server boot via ``start_job_workers``)."""
        if self._jobs_ready:
            return
        self._register_core_job_kinds()
        self._ensure_default_schedules()
        self._jobs_ready = True
        logger.info("Job system initialized (kinds: %s)", ", ".join(registry.registered_kinds()))

    def start_job_workers(self):
        """Start the consumer + scheduler daemons. Called once from ``build_app``. Reconciles
        jobs left mid-flight by a previous process before the consumer can redeliver them."""
        if os.environ.get("DEVICEKIT_DISABLE_JOB_WORKERS", "").lower() in ("1", "true", "yes"):
            logger.warning("Job workers disabled via DEVICEKIT_DISABLE_JOB_WORKERS")
            return
        self.init_jobs()
        try:
            interrupted = JobService.reconcile_interrupted()
            reconciled_runs = self.reconcile_interrupted_runs() if hasattr(
                self, "reconcile_interrupted_runs") else 0
            if interrupted or reconciled_runs:
                logger.info("Reconciled %d interrupted job(s), %d run(s) after restart",
                            interrupted, reconciled_runs)
        except Exception as e:
            logger.warning(f"Job reconciliation skipped: {e}")

        if self._job_consumer is None:
            self._job_consumer = JobConsumer(emit=self._emit_job_event, max_workers=JOB_WORKERS)
            self._job_consumer.start()
        if self._job_scheduler is None:
            self._job_scheduler = JobScheduler(tick_seconds=15)
            self._job_scheduler.start()

    def stop_job_workers(self):
        if self._job_consumer is not None:
            self._job_consumer.stop()
            self._job_consumer = None
        if self._job_scheduler is not None:
            self._job_scheduler.stop()
            self._job_scheduler = None

    def _emit_job_event(self, event_type, job_dict):
        """Broadcast a job status transition on the existing SSE channel so the Jobs view (and
        any run view) updates live."""
        try:
            self.broadcast("job", {"event": event_type, "job": job_dict})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Kind registration
    # ------------------------------------------------------------------
    def register_job_kind(self, kind, handler, replace=True):
        """Register a ``kind → handler(job_dict) -> result`` mapping. Used by core + the SDK."""
        registry.register(kind, handler, replace=replace)

    def unregister_job_kind(self, kind):
        registry.unregister(kind)

    def _register_core_job_kinds(self):
        # Domain handlers live on their own mixins; register whichever the composite provides.
        if hasattr(self, "_job_run_automation"):
            self.register_job_kind("automation.run", self._job_run_automation)
        if hasattr(self, "_job_run_graph"):
            self.register_job_kind("automation.run_graph", self._job_run_graph)
        if hasattr(self, "_job_schedule_tick"):
            self.register_job_kind("automation.schedule.tick", self._job_schedule_tick)
        self.register_job_kind("bundle.retention.prune", self._job_prune_bundles)
        self.register_job_kind("jobs.retention.prune", self._job_prune_jobs)
        if hasattr(self, "reap_stale_agents"):
            self.register_job_kind("agent.heartbeat.reap", self._job_reap_agents)

    def _ensure_default_schedules(self):
        # Automation schedule checker — replaces the old per-mixin daemon thread. Ticks every
        # 30s, enqueues due automation runs (see AutomationMixin.run_due_automation_schedules).
        if hasattr(self, "run_due_automation_schedules"):
            ScheduledJobService.ensure(
                "automation.schedule.tick", "automation.schedule.tick",
                interval_seconds=30, startup_delay_seconds=15,
                owner_type="system", owner_id="core")
        # Housekeeping.
        ScheduledJobService.ensure(
            "bundle.retention.prune", "bundle.retention.prune",
            interval_seconds=86400, startup_delay_seconds=3600,
            owner_type="system", owner_id="core")
        ScheduledJobService.ensure(
            "jobs.retention.prune", "jobs.retention.prune",
            interval_seconds=86400, startup_delay_seconds=3600,
            owner_type="system", owner_id="core")
        # Heartbeat reaper — marks silent agent devices offline (plan 07). Ticks every 30s.
        if hasattr(self, "reap_stale_agents"):
            ScheduledJobService.ensure(
                "agent.heartbeat.reap", "agent.heartbeat.reap",
                interval_seconds=30, startup_delay_seconds=30,
                owner_type="system", owner_id="core")

    # ------------------------------------------------------------------
    # Generic housekeeping handlers
    # ------------------------------------------------------------------
    def _job_reap_agents(self, job):
        evicted = self.reap_stale_agents()
        return {"evicted": evicted, "count": len(evicted)}

    def _job_prune_bundles(self, job):
        if not hasattr(self, "cleanup_old_bundles"):
            return {"removed": 0, "skipped": "no debug-bundle mixin"}
        removed = self.cleanup_old_bundles()
        return {"removed": removed}

    def _job_prune_jobs(self, job):
        return {"pruned": JobService.prune_terminal()}

    # ------------------------------------------------------------------
    # Façade — jobs
    # ------------------------------------------------------------------
    def enqueue_job(self, kind, payload=None, max_attempts=3, priority=0, delay_ms=0,
                    owner_type=None, owner_id=None):
        return JobService.enqueue(
            kind, payload=payload, max_attempts=max_attempts, priority=priority,
            delay_ms=delay_ms, owner_type=owner_type, owner_id=owner_id)

    def get_job(self, job_id, include_payload=True):
        return JobService.get(job_id, include_payload=include_payload)

    def list_jobs(self, status=None, kind=None, owner_type=None, owner_id=None, q=None,
                  limit=50, offset=0):
        return JobService.list(status=status, kind=kind, owner_type=owner_type,
                               owner_id=owner_id, q=q, limit=limit, offset=offset)

    def count_jobs(self, status=None, kind=None, owner_type=None, owner_id=None, q=None):
        return JobService.count(status=status, kind=kind, owner_type=owner_type,
                                owner_id=owner_id, q=q)

    def retry_job(self, job_id):
        return JobService.retry(job_id)

    def cancel_job(self, job_id):
        return JobService.cancel(job_id)

    def job_stats(self):
        return JobService.stats()

    # ------------------------------------------------------------------
    # Façade — scheduled jobs
    # ------------------------------------------------------------------
    def list_scheduled_jobs(self, owner_type=None, owner_id=None):
        return ScheduledJobService.list(owner_type=owner_type, owner_id=owner_id)

    def ensure_scheduled_job(self, name, kind, **kwargs):
        return ScheduledJobService.ensure(name, kind, **kwargs)

    def run_scheduled_job_now(self, scheduled_job_id):
        return ScheduledJobService.run_now(scheduled_job_id)

    def set_scheduled_job_enabled(self, scheduled_job_id, enabled):
        return ScheduledJobService.set_enabled(scheduled_job_id, enabled)

    def delete_scheduled_job(self, scheduled_job_id):
        return ScheduledJobService.delete(scheduled_job_id)

    # ------------------------------------------------------------------
    # Extension pause/resume (plan 03 seam — port of pause_jobs/resume_jobs)
    # ------------------------------------------------------------------
    def pause_jobs(self, owner_type, owner_id):
        return ScheduledJobService.set_enabled_for_owner(owner_type, owner_id, False)

    def resume_jobs(self, owner_type, owner_id):
        return ScheduledJobService.set_enabled_for_owner(owner_type, owner_id, True)
