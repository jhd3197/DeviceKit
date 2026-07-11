"""The generic job consumer — the worker that runs every enqueued Job (port of ServerKit's
``jobs/consumer.py``, with bounded concurrency added).

A daemon thread polls the ``devicekit-system/jobs`` queue; the per-message work is delegated
to the handler registered for the job's ``kind``. Retry / backoff / dead-lettering come from
the Queue Bus; this consumer maps the queue outcome back onto the Job row.

ServerKit ran handlers inline in the poll loop (serial). DeviceKit automations run for
minutes and must not block schedule ticks or other jobs, so claimed messages are dispatched
to a small ``ThreadPoolExecutor`` and the consumer only claims as many as there are free
worker slots — bounded parallelism, no unbounded thread spawning. ``session_scope`` is plain
SQLAlchemy, so no Flask app context is needed on the worker threads.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from devicekit.db import session_scope
from devicekit.jobs import registry
from devicekit.jobs.models import Job
from devicekit.jobs.service import GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
from devicekit.queue_bus.service import QueueBusService

logger = logging.getLogger(__name__)


class JobConsumer:
    """Polls the queue bus for job messages and runs each via its handler."""

    def __init__(self, poll_interval_seconds=1, batch_size=5, max_workers=4, emit=None):
        self.running = False
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self.max_workers = max_workers
        self._emit = emit
        self._executor = None
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._thread = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="job-worker")
        QueueBusService.ensure_queue(GROUP_SLUG, QUEUE_SLUG, config=QUEUE_CONFIG)
        self._thread = threading.Thread(target=self._run, daemon=True, name="job-consumer")
        self._thread.start()
        logger.info("Job consumer started (max_workers=%d)", self.max_workers)

    def stop(self):
        self.running = False
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _run(self):
        while self.running:
            try:
                self.poll_once()
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Job consumer error: {e}")
            time.sleep(self.poll_interval_seconds)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def poll_once(self):
        """Claim up to the number of free worker slots and dispatch each to the pool."""
        # Reclaim any in-flight message whose visibility deadline lapsed (a worker that died
        # without taking the process down) so it can be redelivered.
        try:
            QueueBusService.reap_expired(GROUP_SLUG, QUEUE_SLUG)
        except Exception:
            pass
        with self._inflight_lock:
            free = self.max_workers - self._inflight
        if free <= 0:
            return 0
        messages = QueueBusService.receive(
            GROUP_SLUG, QUEUE_SLUG,
            visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"],
            max_messages=min(self.batch_size, free),
        )
        for message in messages:
            with self._inflight_lock:
                self._inflight += 1
            self._executor.submit(self._worker, message)
        return len(messages)

    def _worker(self, message):
        try:
            self.process_message(message)
        except Exception as e:  # pragma: no cover - per-message isolation
            logger.error(f"Job message {message.get('id')} crashed a worker: {e}")
        finally:
            with self._inflight_lock:
                self._inflight -= 1

    # ------------------------------------------------------------------
    # Message processing (test-callable synchronously)
    # ------------------------------------------------------------------
    def process_message(self, message):
        """Run one job. Safe to call directly (the test-suite does)."""
        payload = message.get("payload") or {}
        job_id = payload.get("job_id")
        if not job_id:
            QueueBusService.complete(GROUP_SLUG, QUEUE_SLUG, message["id"])
            return

        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job:
                QueueBusService.complete(GROUP_SLUG, QUEUE_SLUG, message["id"])
                return
            # Honor a cancellation (or a restart-reconciled terminal state) requested before
            # this message was picked up.
            if job.status in Job.TERMINAL_STATUSES:
                QueueBusService.complete(GROUP_SLUG, QUEUE_SLUG, message["id"])
                return
            kind = job.kind

        handler = registry.get(kind)
        if handler is None:
            # Unroutable — fail without burning retries, and complete the message so it
            # doesn't loop.
            self._mark_terminal_failure(job_id, f"No handler registered for kind {kind!r}")
            QueueBusService.complete(GROUP_SLUG, QUEUE_SLUG, message["id"])
            return

        with session_scope() as s:
            job = s.get(Job, job_id)
            job.status = Job.STATUS_RUNNING
            job.started_at = job.started_at or datetime.utcnow()
            job.attempts = message.get("attempts") or job.attempts or 0
            job.queue_message_id = message["id"]
            job_dict = job.to_dict(include_payload=True)

        self._emit_event("job.running", job_dict)

        try:
            result = handler(job_dict)
            with session_scope() as s:
                job = s.get(Job, job_id)
                if job and job.status == Job.STATUS_RUNNING:
                    job.set_result(result)
                    job.status = Job.STATUS_SUCCEEDED
                    job.completed_at = datetime.utcnow()
                    job.error_message = None
                emitted = job.to_dict(include_payload=True) if job else None
            QueueBusService.complete(GROUP_SLUG, QUEUE_SLUG, message["id"])
            if emitted:
                self._emit_event("job.succeeded", emitted)
        except Exception as e:
            logger.error(f"Job {job_id} ({kind}) failed: {e}")
            self._fail(job_id, message, str(e))

    def _fail(self, job_id, message, error):
        outcome = None
        try:
            outcome = QueueBusService.fail(
                GROUP_SLUG, QUEUE_SLUG, message["id"], error_message=(error or "")[:500])
        except Exception as e:
            logger.error(f"Failed to mark job message failed: {e}")

        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            job.error_message = (error or "")[:2000]
            if outcome and outcome.get("status") == "dead_letter":
                job.status = Job.STATUS_FAILED
                job.completed_at = datetime.utcnow()
                terminal = True
            else:
                # The queue will redeliver after a backoff; reflect that as pending.
                job.status = Job.STATUS_PENDING
                terminal = False
            emitted = job.to_dict(include_payload=True)
        if terminal:
            self._emit_event("job.failed", emitted)

    def _mark_terminal_failure(self, job_id, reason):
        with session_scope() as s:
            job = s.get(Job, job_id)
            if not job:
                return
            job.status = Job.STATUS_FAILED
            job.error_message = reason
            job.completed_at = datetime.utcnow()
            emitted = job.to_dict(include_payload=True)
        self._emit_event("job.failed", emitted)

    def _emit_event(self, event_type, job_dict):
        if self._emit is None:
            return
        try:
            self._emit(event_type, job_dict)
        except Exception:  # pragma: no cover - observability must never break a job
            pass
