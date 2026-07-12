"""Plan 22 phase 5: parallel device fan-out — the dk.device-fan-out node dispatches
one durable job per device branch, concurrency-capped with a per-device timeout, and
collects branch results back into the parent run.

The parent run blocks a consumer slot while its branches execute, so these tests run
the parent's job on a background thread and drain branch jobs from the main thread —
the same shape as the real JobConsumer's worker pool.
"""
import threading
import time

import pytest

from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.workflow import WorkflowMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.jobs import registry
from devicekit.jobs.service import GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
from devicekit.jobs.consumer import JobConsumer
from devicekit.queue_bus.service import QueueBusService


class _App(AutomationMixin, WorkflowMixin, JobsMixin):
    def __init__(self):
        self.events = []

    def broadcast(self, event_type, data):
        self.events.append((event_type, data))


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    yield
    registry.clear()


def _fanout_graph(sub_id, **config):
    cfg = {"automation_id": sub_id, "concurrency": 2, "timeout_seconds": 30}
    cfg.update(config)
    return {
        "version": 1,
        "nodes": [
            {"id": "t", "type": "manual-trigger", "config": {}},
            {"id": "fan", "type": "dk.device-fan-out", "label": "fan", "config": cfg},
        ],
        "edges": [{"id": "e1", "source": "t", "target": "fan"}],
        "meta": {},
    }


def _receive(max_messages=20):
    return QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"],
        max_messages=max_messages)


def _run_parent_with_branch_drain(app, parent_run, timeout=30, drain_branches=True):
    """Process the parent's graph job on a worker thread while this thread plays the
    other consumer workers, draining branch jobs as they appear."""
    consumer = JobConsumer(emit=app._emit_job_event)
    msgs = _receive()
    assert len(msgs) == 1, "expected exactly the parent job on the queue"
    parent_thread = threading.Thread(target=consumer.process_message, args=(msgs[0],))
    parent_thread.start()
    deadline = time.time() + timeout
    while parent_thread.is_alive() and time.time() < deadline:
        if drain_branches:
            for m in _receive():
                consumer.process_message(m)
        time.sleep(0.05)
    parent_thread.join(timeout=5)
    assert not parent_thread.is_alive(), "parent fan-out job never finished"
    return app.get_automation_run(parent_run["id"])


def test_fan_out_runs_branch_per_device(fresh_db):
    app = _App()
    app.init_jobs()
    sub = app.create_automation("Per device", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])
    parent = app.create_automation("Sweep", graph=_fanout_graph(
        sub["id"], devices="d1, d2, d3"))

    run = app.enqueue_run(parent["id"])
    got = _run_parent_with_branch_drain(app, run)
    assert got["status"] == "completed"

    fan = next(r for r in got["step_results"] if r["node_id"] == "fan")
    assert fan["status"] == "completed"

    # One sub-run per device, linked back to the parent.
    all_branch_runs = []
    for device_id in ("d1", "d2", "d3"):
        branch = app.list_automation_runs(automation_id=sub["id"], device_id=device_id)
        assert len(branch) == 1
        assert branch[0]["status"] == "completed"
        assert branch[0]["trigger"]["type"] == "fanout"
        assert branch[0]["trigger"]["payload"]["parent_run_id"] == run["id"]
        all_branch_runs.append(branch[0]["id"])
    assert len(set(all_branch_runs)) == 3


def test_fan_out_collects_partial_failures(fresh_db):
    app = _App()
    app.init_jobs()

    def _fail_on_d2(client, config, device_id):
        if device_id == "d2":
            raise RuntimeError(f"device {device_id} exploded")
        return "ok"

    app.register_step_type("fail_on_d2", {
        "label": "Fails on d2", "category": "Test", "config": {},
        "execute": _fail_on_d2})
    try:
        sub = app.create_automation("Fragile", steps=[
            {"id": "s1", "type": "fail_on_d2", "label": "x", "config": {}},
        ])
        parent = app.create_automation("Sweep", graph=_fanout_graph(
            sub["id"], devices="d1, d2, d3"))

        run = app.enqueue_run(parent["id"])
        got = _run_parent_with_branch_drain(app, run)

        # The fan-out node routed an error envelope (a routed outcome, not a raise) —
        # with no error branch wired, the node itself still completed.
        fan = next(r for r in got["step_results"] if r["node_id"] == "fan")
        assert fan["status"] == "completed"
        branch_d2 = app.list_automation_runs(automation_id=sub["id"], device_id="d2")[0]
        assert branch_d2["status"] == "failed"
        for ok_dev in ("d1", "d3"):
            assert app.list_automation_runs(
                automation_id=sub["id"], device_id=ok_dev)[0]["status"] == "completed"
    finally:
        app.unregister_step_type("fail_on_d2")


def test_fan_out_times_out_stuck_branches(fresh_db):
    app = _App()
    app.init_jobs()
    sub = app.create_automation("Never picked up", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])
    parent = app.create_automation("Sweep", graph=_fanout_graph(
        sub["id"], devices="d1, d2", timeout_seconds=0.5))

    run = app.enqueue_run(parent["id"])
    # Branch jobs are never drained — they sit queued past the per-device timeout.
    got = _run_parent_with_branch_drain(app, run, drain_branches=False)
    assert got["status"] == "completed"   # error envelope, not a crash

    for device_id in ("d1", "d2"):
        branch = app.list_automation_runs(automation_id=sub["id"], device_id=device_id)[0]
        assert branch["status"] == "cancelled"   # timed-out branches get cancelled


def test_fan_out_devices_from_trigger_expression(fresh_db):
    app = _App()
    app.init_jobs()
    sub = app.create_automation("Per device", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])
    parent = app.create_automation("Sweep", graph=_fanout_graph(
        sub["id"], devices="trigger.devices"))

    run = app.enqueue_run(parent["id"], trigger_type="webhook",
                          trigger={"devices": ["da", "db"]})
    got = _run_parent_with_branch_drain(app, run)
    assert got["status"] == "completed"
    for device_id in ("da", "db"):
        assert app.list_automation_runs(automation_id=sub["id"],
                                        device_id=device_id)


def test_fan_out_rejects_self_reference(fresh_db):
    app = _App()
    app.init_jobs()
    parent = app.create_automation("Self sweep")
    app.save_automation_graph(parent["id"], _fanout_graph(parent["id"], devices="d1"))

    run = app.enqueue_run(parent["id"])
    got = _run_parent_with_branch_drain(app, run)
    fan = next(r for r in got["step_results"] if r["node_id"] == "fan")
    assert fan["status"] == "completed"
    # No branch runs were created — the cycle guard refused before dispatch.
    assert app.list_automation_runs(automation_id=parent["id"], device_id="d1") == []


def test_fan_out_requires_targeting(fresh_db):
    app = _App()
    app.init_jobs()
    sub = app.create_automation("Per device", steps=[])
    parent = app.create_automation("Sweep", graph=_fanout_graph(sub["id"]))

    run = app.enqueue_run(parent["id"])
    got = _run_parent_with_branch_drain(app, run)
    fan = next(r for r in got["step_results"] if r["node_id"] == "fan")
    # Error envelope names the misconfiguration.
    assert fan["status"] == "completed"
    assert app.list_automation_runs(automation_id=sub["id"]) == []
