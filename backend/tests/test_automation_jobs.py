"""Automations run on the job system: execute enqueues a run job, the handler drives the
step loop to completion, a queued run can be cancelled, and a run interrupted by a restart
reconciles to a coherent 'failed' status instead of vanishing (plan 05).

Uses ``wait`` steps only, so no real device is needed; the consumer is driven synchronously.
"""
import pytest

from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.jobs import registry
from devicekit.jobs.service import GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
from devicekit.jobs.consumer import JobConsumer
from devicekit.queue_bus.service import QueueBusService


class _App(AutomationMixin, JobsMixin):
    """Automation + jobs composite with a no-op broadcast (no SSE transport in tests)."""

    def __init__(self):
        self.events = []

    def broadcast(self, event_type, data):
        self.events.append((event_type, data.get("event")))


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    yield
    registry.clear()


def _wait_steps():
    return [
        {"id": "s1", "type": "wait", "label": "w1", "config": {"delay": 1}},
        {"id": "s2", "type": "wait", "label": "w2", "config": {"delay": 1}},
    ]


def _drain(consumer):
    msgs = QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"], max_messages=10)
    for m in msgs:
        consumer.process_message(m)
    return len(msgs)


def test_execute_enqueues_and_runs_to_completion(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Flow", steps=_wait_steps())

    run = app.execute_automation(a["id"], "serial-1")
    assert run["status"] == "queued"
    # A run job was enqueued for it.
    jobs = app.list_jobs(kind="automation.run")
    assert len(jobs) == 1
    assert jobs[0]["owner_id"] == run["id"]

    consumer = JobConsumer(emit=app._emit_job_event)
    assert _drain(consumer) == 1

    got = app.get_automation_run(run["id"])
    assert got["status"] == "completed"
    assert got["completed_steps"] == 2
    # Job succeeded and broadcast a transition.
    assert app.list_jobs(status="succeeded")
    assert ("job", "job.succeeded") in app.events


def test_unknown_step_fails_the_run(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Bad", steps=[
        {"id": "s1", "type": "does_not_exist", "label": "x", "config": {}},
    ])
    run = app.execute_automation(a["id"], "serial-1")
    consumer = JobConsumer()
    _drain(consumer)
    got = app.get_automation_run(run["id"])
    assert got["status"] == "failed"
    assert got["error"]


def test_cancel_queued_run(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Flow", steps=_wait_steps())
    run = app.execute_automation(a["id"], "serial-1")

    assert app.cancel_automation_run(run["id"]) is True
    assert app.get_automation_run(run["id"])["status"] == "cancelled"

    # The consumer must skip the cancelled run's message.
    consumer = JobConsumer()
    _drain(consumer)
    assert app.get_automation_run(run["id"])["status"] == "cancelled"


def test_run_survives_restart_as_failed(fresh_db, restart):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Flow", steps=_wait_steps())
    run = app.execute_automation(a["id"], "serial-1")  # left queued, "backend restarts"

    restart(fresh_db)

    reloaded = _App()
    n = reloaded.reconcile_interrupted_runs()
    assert n == 1
    got = reloaded.get_automation_run(run["id"])
    assert got["status"] == "failed"
    assert "restart" in got["error"].lower()


def test_schedule_tick_enqueues_run(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Nightly", steps=_wait_steps())
    # interval 0 -> next_run_at == now -> immediately due.
    app.create_schedule(a["id"], "serial-1", interval_minutes=0, enabled=True)

    fired = app.run_due_automation_schedules()
    assert fired == 1
    # A run record + its automation.run job now exist.
    runs = app.list_automation_runs(automation_id=a["id"])
    assert len(runs) == 1
    assert app.list_jobs(kind="automation.run")

    # And the whole thing drains to completion.
    consumer = JobConsumer()
    _drain(consumer)
    assert app.get_automation_run(runs[0]["id"])["status"] == "completed"
