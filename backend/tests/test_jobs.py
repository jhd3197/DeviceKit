"""Unified job system: enqueue -> consumer -> handler dispatch, failure -> retry ->
dead-letter -> job failed, cancel-before-pickup, retry, restart reconciliation, and
prune (plan 05).

The consumer is driven synchronously (``process_message`` on each claimed message) so no
daemon threads run in the suite — the same seam ServerKit's tests use.
"""
import pytest

from devicekit.jobs import registry
from devicekit.jobs.service import JobService, GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
from devicekit.jobs.consumer import JobConsumer
from devicekit.jobs.models import Job
from devicekit.queue_bus.service import QueueBusService


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    yield
    registry.clear()


def _drain(consumer, max_messages=10):
    msgs = QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"],
        max_messages=max_messages)
    for m in msgs:
        consumer.process_message(m)
    return len(msgs)


def test_enqueue_runs_handler_and_succeeds(fresh_db):
    seen = {}
    registry.register("echo", lambda job: {"v": job["payload"]["v"]})
    consumer = JobConsumer(emit=lambda et, j: seen.setdefault(et, j))

    job = JobService.enqueue("echo", payload={"v": 7})
    assert job["status"] == "pending"
    assert _drain(consumer) == 1

    got = JobService.get(job["id"])
    assert got["status"] == "succeeded"
    assert got["result"] == {"v": 7}
    assert "job.succeeded" in seen


def test_unroutable_kind_fails_without_retry(fresh_db):
    consumer = JobConsumer()
    job = JobService.enqueue("no.handler", payload={})
    _drain(consumer)
    got = JobService.get(job["id"])
    assert got["status"] == "failed"
    assert "No handler" in got["error_message"]


def test_failing_handler_dead_letters_to_failed(fresh_db):
    def boom(job):
        raise RuntimeError("kaboom")

    registry.register("boom", boom)
    consumer = JobConsumer()
    # max_attempts=1 so the first failure dead-letters immediately.
    job = JobService.enqueue("boom", payload={}, max_attempts=1)
    _drain(consumer)
    got = JobService.get(job["id"])
    assert got["status"] == "failed"
    assert "kaboom" in got["error_message"]


def test_cancel_before_pickup_is_skipped(fresh_db):
    ran = {"n": 0}

    def count(job):
        ran["n"] += 1

    registry.register("count", count)
    consumer = JobConsumer()
    job = JobService.enqueue("count", payload={})
    JobService.cancel(job["id"])
    assert JobService.get(job["id"])["status"] == "cancelled"
    _drain(consumer)
    # Handler must not have run for a cancelled job.
    assert ran["n"] == 0
    assert JobService.get(job["id"])["status"] == "cancelled"


def test_retry_reenqueues_failed_job(fresh_db):
    calls = {"n": 0}

    def flaky(job):
        calls["n"] += 1
        raise RuntimeError("nope")

    registry.register("flaky", flaky)
    consumer = JobConsumer()
    job = JobService.enqueue("flaky", payload={}, max_attempts=1)
    _drain(consumer)
    assert JobService.get(job["id"])["status"] == "failed"

    retried = JobService.retry(job["id"])
    assert retried["status"] == "pending"
    _drain(consumer)
    assert calls["n"] == 2  # ran again


def test_reconcile_interrupted(fresh_db):
    registry.register("noop", lambda job: None)
    JobService.enqueue("noop", payload={})  # stays pending (never drained)
    n = JobService.reconcile_interrupted()
    assert n == 1
    # The reconciled job is now failed with a reason.
    jobs = JobService.list(status="failed")
    assert len(jobs) == 1
    assert "restart" in jobs[0]["error_message"].lower()


def test_stats_and_list_filters(fresh_db):
    registry.register("echo", lambda job: None)
    JobService.enqueue("echo", payload={}, owner_type="thing", owner_id="a")
    JobService.enqueue("echo", payload={}, owner_type="thing", owner_id="b")
    assert JobService.count(owner_type="thing") == 2
    assert JobService.count(owner_id="a") == 1
    stats = JobService.stats()
    assert stats["by_kind"]["echo"] == 2


def test_prune_terminal(fresh_db):
    import datetime as dt
    from devicekit.db import session_scope
    registry.register("echo", lambda job: None)
    job = JobService.enqueue("echo", payload={})
    # Force it terminal + old.
    with session_scope() as s:
        row = s.get(Job, job["id"])
        row.status = Job.STATUS_SUCCEEDED
        row.completed_at = dt.datetime.utcnow() - dt.timedelta(days=60)
    pruned = JobService.prune_terminal(retention_days=14)
    assert pruned == 1
    assert JobService.get(job["id"]) is None
