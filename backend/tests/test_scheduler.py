"""Scheduler: idempotent ensure that preserves the clock across a restart, due/fire, the
tick loop, and owner-scoped pause/resume (plan 05)."""
import pytest

from devicekit.jobs import registry
from devicekit.jobs.service import ScheduledJobService, JobService, GROUP_SLUG, QUEUE_SLUG
from devicekit.jobs.scheduler import JobScheduler
from devicekit.jobs.consumer import JobConsumer
from devicekit.queue_bus.service import QueueBusService


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    yield
    registry.clear()


def test_ensure_is_idempotent_and_preserves_clock(fresh_db, restart):
    registry.register("tick", lambda job: None)
    first = ScheduledJobService.ensure("nightly", "tick", interval_seconds=3600)
    original_next = first["next_run_at"]
    assert original_next is not None

    # Re-ensure with a different cadence: next_run_at is PRESERVED (redeploys don't reset).
    second = ScheduledJobService.ensure("nightly", "tick", interval_seconds=60)
    assert second["next_run_at"] == original_next
    assert second["interval_seconds"] == 60

    restart(fresh_db)
    after = ScheduledJobService.ensure("nightly", "tick", interval_seconds=60)
    assert after["next_run_at"] == original_next  # survived the restart


def test_due_and_fire_advances_clock(fresh_db):
    registry.register("tick", lambda job: None)
    # startup_delay 0 -> immediately due.
    sch = ScheduledJobService.ensure("now", "tick", interval_seconds=3600, startup_delay_seconds=0)
    due = ScheduledJobService.due()
    assert any(d["id"] == sch["id"] for d in due)

    job = ScheduledJobService.fire(sch["id"])
    assert job["kind"] == "tick"
    assert job["owner_type"] == "schedule"
    # Clock advanced ~an hour into the future -> no longer due.
    assert not any(d["id"] == sch["id"] for d in ScheduledJobService.due())


def test_tick_enqueues_due_jobs(fresh_db):
    fired_kinds = []
    registry.register("tick", lambda job: fired_kinds.append(job["kind"]))
    ScheduledJobService.ensure("a", "tick", interval_seconds=3600, startup_delay_seconds=0)
    ScheduledJobService.ensure("b", "tick", interval_seconds=3600, startup_delay_seconds=0)

    scheduler = JobScheduler()
    fired = scheduler.tick()
    assert fired == 2

    # Drain the two enqueued jobs.
    consumer = JobConsumer()
    msgs = QueueBusService.receive(GROUP_SLUG, QUEUE_SLUG, visibility_timeout_ms=60000, max_messages=10)
    for m in msgs:
        consumer.process_message(m)
    assert len(fired_kinds) == 2


def test_owner_pause_resume(fresh_db):
    registry.register("tick", lambda job: None)
    ScheduledJobService.ensure("x", "tick", interval_seconds=3600, startup_delay_seconds=0,
                               owner_type="extension", owner_id="ext-a")
    ScheduledJobService.ensure("y", "tick", interval_seconds=3600, startup_delay_seconds=0,
                               owner_type="extension", owner_id="ext-a")
    assert ScheduledJobService.set_enabled_for_owner("extension", "ext-a", False) == 2
    # Paused schedules are not due.
    assert ScheduledJobService.due() == []
    ScheduledJobService.set_enabled_for_owner("extension", "ext-a", True)
    assert len(ScheduledJobService.due()) == 2
