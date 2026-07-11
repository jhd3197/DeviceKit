"""Producer + management API for the unified job system (port of ServerKit's
``jobs/service.py``).

``JobService`` is the one entry point to enqueue work; ``ScheduledJobService`` manages
periodic schedules. Both are non-blocking: they persist a row and (for jobs) publish a thin
``{'job_id': ...}`` pointer onto the Queue Bus. Every method returns plain dicts (not ORM
rows) because DeviceKit's ``session_scope`` closes the session per operation.
"""
import logging
import uuid
from datetime import datetime, timedelta

from devicekit.db import session_scope
from devicekit.jobs.models import Job, ScheduledJob
from devicekit.queue_bus.service import QueueBusService

logger = logging.getLogger(__name__)

GROUP_SLUG = "devicekit-system"
QUEUE_SLUG = "jobs"
# Jobs (automations) run far longer than a webhook POST, so the visibility window before the
# queue considers an in-flight message abandoned is generous. Single-process: a crash is a
# full restart (boot reconciliation handles interrupted runs), so this only needs to exceed
# a normal job's wall-clock to avoid mid-run redelivery.
QUEUE_CONFIG = {"max_attempts": 3, "visibility_timeout_ms": 3600000}


def _new_correlation_id():
    return uuid.uuid4().hex


class JobService:

    @classmethod
    def enqueue(cls, kind, payload=None, max_attempts=3, priority=0, delay_ms=0,
                owner_type=None, owner_id=None, correlation_id=None, job_id=None):
        """Persist a Job and publish it onto the Queue Bus. Returns the Job dict."""
        QueueBusService.ensure_queue(GROUP_SLUG, QUEUE_SLUG, config=QUEUE_CONFIG)
        with session_scope() as s:
            job = Job(
                id=job_id or str(uuid.uuid4()),
                kind=kind,
                status=Job.STATUS_PENDING,
                max_attempts=max_attempts,
                priority=priority,
                owner_type=owner_type,
                owner_id=str(owner_id) if owner_id is not None else None,
                correlation_id=correlation_id or _new_correlation_id(),
            )
            job.set_payload(payload or {})
            if delay_ms:
                job.scheduled_at = datetime.utcnow() + timedelta(milliseconds=delay_ms)
            s.add(job)
            s.flush()
            job_dict = job.to_dict(include_payload=True)

        msg = QueueBusService.send(
            GROUP_SLUG, QUEUE_SLUG, {"job_id": job_dict["id"]},
            priority=priority, delay_ms=delay_ms, max_attempts=max_attempts,
        )
        if isinstance(msg, dict):
            with session_scope() as s:
                row = s.get(Job, job_dict["id"])
                if row:
                    row.queue_message_id = msg.get("id")
        return job_dict

    @classmethod
    def republish(cls, job_id, delay_ms=0):
        """Send a fresh queue message for an existing job (retry path)."""
        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job:
                return None
            priority, max_attempts = job.priority or 0, job.max_attempts
        QueueBusService.ensure_queue(GROUP_SLUG, QUEUE_SLUG, config=QUEUE_CONFIG)
        msg = QueueBusService.send(
            GROUP_SLUG, QUEUE_SLUG, {"job_id": job_id},
            priority=priority, delay_ms=delay_ms, max_attempts=max_attempts,
        )
        if isinstance(msg, dict):
            with session_scope() as s:
                row = s.get(Job, job_id)
                if row:
                    row.queue_message_id = msg.get("id")
        return msg

    @classmethod
    def get(cls, job_id, include_payload=True):
        with session_scope() as s:
            job = s.get(Job, job_id)
            return job.to_dict(include_payload=include_payload) if job else None

    @staticmethod
    def _apply_filters(query, status=None, kind=None, owner_type=None, owner_id=None, q=None):
        from sqlalchemy import func, or_
        if status:
            query = query.filter(Job.status == status)
        if kind:
            query = query.filter(Job.kind == kind)
        if owner_type:
            query = query.filter(Job.owner_type == owner_type)
        if owner_id is not None:
            query = query.filter(Job.owner_id == str(owner_id))
        if q and str(q).strip():
            like = f"%{str(q).strip().lower()}%"
            query = query.filter(or_(
                func.lower(Job.kind).like(like),
                func.lower(Job.owner_type).like(like),
                func.lower(Job.owner_id).like(like),
            ))
        return query

    @classmethod
    def list(cls, status=None, kind=None, owner_type=None, owner_id=None, q=None,
             limit=50, offset=0, include_payload=False):
        with session_scope() as s:
            query = cls._apply_filters(s.query(Job), status, kind, owner_type, owner_id, q)
            rows = query.order_by(Job.created_at.desc()).limit(limit).offset(offset).all()
            return [r.to_dict(include_payload=include_payload) for r in rows]

    @classmethod
    def count(cls, status=None, kind=None, owner_type=None, owner_id=None, q=None):
        with session_scope() as s:
            query = cls._apply_filters(s.query(Job), status, kind, owner_type, owner_id, q)
            return query.count()

    @classmethod
    def cancel(cls, job_id):
        """Mark a pending/running job cancelled. Cannot interrupt a handler already
        executing (that needs a cooperative cancel signal) — it stops future attempts and is
        skipped at the next queue pickup."""
        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job:
                return None
            if job.status in Job.ACTIVE_STATUSES:
                job.status = Job.STATUS_CANCELLED
                job.completed_at = datetime.utcnow()
            return job.to_dict()

    @classmethod
    def retry(cls, job_id):
        """Re-enqueue a failed/cancelled job as a fresh attempt."""
        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job:
                return None
            if job.status not in (Job.STATUS_FAILED, Job.STATUS_CANCELLED):
                return job.to_dict()
            job.status = Job.STATUS_PENDING
            job.error_message = None
            job.started_at = None
            job.completed_at = None
            result = job.to_dict()
        cls.republish(job_id)
        return result

    @classmethod
    def stats(cls):
        from sqlalchemy import func
        with session_scope() as s:
            by_status = dict(s.query(Job.status, func.count(Job.id)).group_by(Job.status).all())
            by_kind = dict(s.query(Job.kind, func.count(Job.id)).group_by(Job.kind).all())
        return {"by_status": by_status, "by_kind": by_kind, "total": sum(by_status.values())}

    @classmethod
    def reconcile_interrupted(cls, reason="Backend restarted during run"):
        """At boot, fail any job still marked pending/running from a previous process — its
        in-memory execution state is gone. Returns the count. The handler additionally
        guards against a redelivered message re-running a now-terminal job."""
        with session_scope() as s:
            interrupted = (s.query(Job)
                           .filter(Job.status.in_(Job.ACTIVE_STATUSES))
                           .all())
            n = 0
            for job in interrupted:
                job.status = Job.STATUS_FAILED
                job.error_message = reason
                job.completed_at = datetime.utcnow()
                n += 1
            return n

    @classmethod
    def prune_terminal(cls, retention_days=14, batch_size=5000):
        """Prune accumulated terminal jobs so scheduler-tick rows don't grow without bound.
        Succeeded/cancelled jobs are kept ``retention_days``; failed jobs 3x as long (worth
        keeping longer for diagnosis). Active rows are never touched. Deletes in batches.
        Returns the count."""
        from sqlalchemy import func
        now = datetime.utcnow()
        age = func.coalesce(Job.completed_at, Job.created_at)
        specs = [
            ((Job.STATUS_SUCCEEDED, Job.STATUS_CANCELLED), now - timedelta(days=retention_days)),
            ((Job.STATUS_FAILED,), now - timedelta(days=retention_days * 3)),
        ]
        deleted = 0
        for statuses, cutoff in specs:
            while True:
                with session_scope() as s:
                    ids = [row[0] for row in (
                        s.query(Job.id)
                        .filter(Job.status.in_(statuses))
                        .filter(age < cutoff)
                        .limit(batch_size).all())]
                    if not ids:
                        break
                    deleted += (s.query(Job).filter(Job.id.in_(ids))
                                .delete(synchronize_session=False))
                if len(ids) < batch_size:
                    break
        return deleted


class ScheduledJobService:

    @classmethod
    def ensure(cls, name, kind, interval_seconds=None, cron=None, payload=None,
               max_attempts=1, startup_delay_seconds=0, enabled=True,
               owner_type=None, owner_id=None):
        """Idempotently create/update a periodic schedule keyed by ``name``.

        Updates cadence/kind on an existing row but PRESERVES its ``next_run_at`` /
        ``last_run_at`` and the admin's ``enabled`` toggle so a restart doesn't reset the
        clock. On first creation, seeds ``next_run_at`` honoring ``startup_delay_seconds``.
        """
        with session_scope() as s:
            scheduled = s.query(ScheduledJob).filter_by(name=name).first()
            created = scheduled is None
            if created:
                scheduled = ScheduledJob(name=name)
                s.add(scheduled)
            scheduled.kind = kind
            scheduled.schedule_kind = (
                ScheduledJob.SCHEDULE_CRON if cron else ScheduledJob.SCHEDULE_INTERVAL)
            scheduled.interval_seconds = interval_seconds
            scheduled.cron = cron
            scheduled.max_attempts = max_attempts
            if owner_type is not None:
                scheduled.owner_type = owner_type
            if owner_id is not None:
                scheduled.owner_id = str(owner_id)
            if payload is not None:
                scheduled.set_payload(payload)
            if created:
                scheduled.enabled = enabled
                scheduled.next_run_at = datetime.utcnow() + timedelta(
                    seconds=startup_delay_seconds or 0)
            s.flush()
            return scheduled.to_dict()

    @classmethod
    def get(cls, scheduled_job_id):
        with session_scope() as s:
            sch = s.get(ScheduledJob, scheduled_job_id)
            return sch.to_dict() if sch else None

    @classmethod
    def list(cls, owner_type=None, owner_id=None):
        with session_scope() as s:
            q = s.query(ScheduledJob)
            if owner_type:
                q = q.filter(ScheduledJob.owner_type == owner_type)
            if owner_id is not None:
                q = q.filter(ScheduledJob.owner_id == str(owner_id))
            return [sch.to_dict() for sch in q.order_by(ScheduledJob.name.asc()).all()]

    @classmethod
    def due(cls, now=None):
        """Return dicts for enabled schedules whose ``next_run_at`` has passed."""
        now = now or datetime.utcnow()
        with session_scope() as s:
            rows = (s.query(ScheduledJob)
                    .filter(ScheduledJob.enabled.is_(True))
                    .filter(ScheduledJob.next_run_at.isnot(None))
                    .filter(ScheduledJob.next_run_at <= now)
                    .all())
            return [r.to_dict() for r in rows]

    @classmethod
    def fire(cls, scheduled_job_id, now=None):
        """Enqueue a Job for one schedule and advance its ``next_run_at``. Returns the
        enqueued Job dict (or None if the schedule vanished)."""
        now = now or datetime.utcnow()
        with session_scope() as s:
            scheduled = s.get(ScheduledJob, scheduled_job_id)
            if not scheduled:
                return None
            kind = scheduled.kind
            payload = scheduled.get_payload()
            max_attempts = scheduled.max_attempts
            name = scheduled.name
        job = JobService.enqueue(
            kind, payload=payload, max_attempts=max_attempts,
            owner_type="schedule", owner_id=name,
        )
        with session_scope() as s:
            scheduled = s.get(ScheduledJob, scheduled_job_id)
            if scheduled:
                scheduled.last_run_at = now
                scheduled.last_job_id = job["id"]
                scheduled.next_run_at = scheduled.compute_next_run(now)
        # Tag the job with its originating schedule id (best-effort).
        with session_scope() as s:
            row = s.get(Job, job["id"])
            if row:
                row.scheduled_job_id = scheduled_job_id
        return job

    @classmethod
    def run_now(cls, scheduled_job_id):
        return cls.fire(scheduled_job_id)

    @classmethod
    def set_enabled(cls, scheduled_job_id, enabled):
        with session_scope() as s:
            scheduled = s.get(ScheduledJob, scheduled_job_id)
            if not scheduled:
                return None
            scheduled.enabled = bool(enabled)
            if enabled and not scheduled.next_run_at:
                scheduled.next_run_at = datetime.utcnow()
            return scheduled.to_dict()

    @classmethod
    def set_enabled_for_owner(cls, owner_type, owner_id, enabled):
        """Pause/resume every schedule owned by (owner_type, owner_id) as a set — the
        extension pause_jobs/resume_jobs hook. Returns the number affected."""
        with session_scope() as s:
            rows = (s.query(ScheduledJob)
                    .filter(ScheduledJob.owner_type == owner_type)
                    .filter(ScheduledJob.owner_id == str(owner_id))
                    .all())
            for sch in rows:
                sch.enabled = bool(enabled)
                if enabled and not sch.next_run_at:
                    sch.next_run_at = datetime.utcnow()
            return len(rows)

    @classmethod
    def delete(cls, scheduled_job_id):
        with session_scope() as s:
            sch = s.get(ScheduledJob, scheduled_job_id)
            if not sch:
                return False
            s.delete(sch)
            return True

    @classmethod
    def delete_by_name(cls, name):
        with session_scope() as s:
            sch = s.query(ScheduledJob).filter_by(name=name).first()
            if not sch:
                return False
            s.delete(sch)
            return True
