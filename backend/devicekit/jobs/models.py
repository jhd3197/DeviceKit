"""Models for the unified background-job system (port of ServerKit's ``jobs/models.py``).

``Job`` is a persisted unit of work with a stable lifecycle
(``pending → running → succeeded | failed | cancelled``). The Queue Bus is the transport:
enqueuing a Job publishes a thin ``{'job_id': ...}`` message; the ``JobConsumer`` loads the
row and dispatches by ``kind``. Retry / backoff / dead-lettering are inherited from the
queue — the Job row mirrors the outcome so there is a single place to observe all
background work.

``ScheduledJob`` is the periodic side: one ticker enqueues a Job for each due schedule,
replacing the per-domain daemon threads that each ran their own ``while True: sleep`` loop.

Adapted to DeviceKit: plain SQLAlchemy on the shared ``Base``, driven through
``session_scope``. Timestamps stay ``DateTime`` (UTC) — the scheduler/consumer logic is
datetime arithmetic — but ``to_dict`` also emits epoch seconds so the frontend Jobs view
matches the ``time.time()`` convention the rest of the API uses.
"""
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime

from devicekit.db import Base


def _epoch(dt):
    return dt.timestamp() if dt else None


class Job(Base):
    __tablename__ = "jobs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED)
    ACTIVE_STATUSES = (STATUS_PENDING, STATUS_RUNNING)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(80), nullable=False, index=True)
    status = Column(String(20), default=STATUS_PENDING, nullable=False, index=True)

    payload = Column(Text, default="{}")
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    priority = Column(Integer, default=0)

    # Loose ownership for filtering ("jobs for this device / automation-run / schedule").
    owner_type = Column(String(40), nullable=True, index=True)
    owner_id = Column(String(64), nullable=True, index=True)

    # Backreference to the schedule that spawned this job, if periodic.
    scheduled_job_id = Column(Integer, nullable=True, index=True)

    correlation_id = Column(String(64), nullable=True, index=True)
    queue_message_id = Column(String(36), nullable=True)

    scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_payload(self):
        try:
            return json.loads(self.payload) if self.payload else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def set_payload(self, payload):
        self.payload = json.dumps(payload or {})

    def get_result(self):
        try:
            return json.loads(self.result) if self.result else None
        except (TypeError, json.JSONDecodeError):
            return None

    def set_result(self, result):
        """Store a JSON-serializable result; fall back to a repr so a weird return value
        never blocks marking a job done."""
        if result is None:
            self.result = None
            return
        try:
            self.result = json.dumps(result)
        except (TypeError, ValueError):
            self.result = json.dumps({"repr": str(result)[:2000]})

    @property
    def duration(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self, include_payload=False):
        data = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "priority": self.priority,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "scheduled_job_id": self.scheduled_job_id,
            "correlation_id": self.correlation_id,
            "result": self.get_result(),
            "error_message": self.error_message,
            "created_at": _epoch(self.created_at),
            "started_at": _epoch(self.started_at),
            "completed_at": _epoch(self.completed_at),
            "updated_at": _epoch(self.updated_at),
            "duration": self.duration,
        }
        if include_payload:
            data["payload"] = self.get_payload()
        return data


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    SCHEDULE_INTERVAL = "interval"
    SCHEDULE_CRON = "cron"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), unique=True, nullable=False)  # stable upsert key
    kind = Column(String(80), nullable=False)               # job kind to enqueue
    schedule_kind = Column(String(20), default=SCHEDULE_INTERVAL, nullable=False)
    interval_seconds = Column(Integer, nullable=True)
    cron = Column(String(120), nullable=True)
    payload = Column(Text, default="{}")
    max_attempts = Column(Integer, default=1, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    # Loose ownership so an extension's schedules can be paused/resumed as a set.
    owner_type = Column(String(40), nullable=True, index=True)
    owner_id = Column(String(64), nullable=True, index=True)

    next_run_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    last_job_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_payload(self):
        try:
            return json.loads(self.payload) if self.payload else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def set_payload(self, payload):
        self.payload = json.dumps(payload or {})

    def compute_next_run(self, base=None):
        base = base or datetime.utcnow()
        if self.schedule_kind == self.SCHEDULE_CRON and self.cron:
            try:
                from croniter import croniter
                if croniter.is_valid(self.cron):
                    return croniter(self.cron, base).get_next(datetime)
            except ImportError:
                pass
            # Cron invalid / croniter unavailable — back off an hour rather than hot-looping.
            return base + timedelta(hours=1)
        return base + timedelta(seconds=self.interval_seconds or 3600)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "schedule_kind": self.schedule_kind,
            "interval_seconds": self.interval_seconds,
            "cron": self.cron,
            "enabled": bool(self.enabled),
            "max_attempts": self.max_attempts,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "next_run_at": _epoch(self.next_run_at),
            "last_run_at": _epoch(self.last_run_at),
            "last_job_id": self.last_job_id,
        }
