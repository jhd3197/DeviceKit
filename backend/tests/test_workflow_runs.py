"""Plan 22 phase 1: graph automations run as durable jobs — a stored WorkflowDoc
dispatches through ``execute_automation`` onto the ``automation.run_graph`` kind, run
records persist per-node results, cancel works pre-pickup, and graph docs survive
clone/export/import round-trips.
"""
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


def _graph_doc():
    return {
        "version": 1,
        "nodes": [
            {"id": "t", "type": "manual-trigger", "config": {}},
            {"id": "w1", "type": "dk.wait", "label": "w1", "config": {"delay": 1}},
            {"id": "w2", "type": "dk.wait", "label": "w2", "config": {"delay": 1}},
        ],
        "edges": [
            {"id": "e1", "source": "t", "target": "w1"},
            {"id": "e2", "source": "w1", "target": "w2"},
        ],
        "meta": {"revision": 1},
    }


def _drain(consumer):
    msgs = QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"], max_messages=10)
    for m in msgs:
        consumer.process_message(m)
    return len(msgs)


def test_graph_automation_runs_via_execute_automation(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Graph flow", graph=_graph_doc())

    # The stable /run entry point dispatches graph automations to the workflow engine.
    run = app.execute_automation(a["id"], "serial-1")
    assert run["status"] == "queued"
    assert run["kind"] == "graph"
    jobs = app.list_jobs(kind="automation.run_graph")
    assert len(jobs) == 1 and jobs[0]["owner_id"] == run["id"]

    _drain(JobConsumer(emit=app._emit_job_event))

    got = app.get_automation_run(run["id"])
    assert got["status"] == "completed"
    assert got["kind"] == "graph"
    assert got["completed_steps"] == 3
    statuses = {r["node_id"]: r["status"] for r in got["step_results"]}
    assert statuses == {"t": "completed", "w1": "completed", "w2": "completed"}
    # Live run events were broadcast in tramo RunEvent shapes.
    run_events = [d for (t, d) in app.events if t == "automation_run"]
    assert any(e.get("type") == "run-start" for e in run_events)
    assert any(e.get("type") == "run-end" and e.get("ok") for e in run_events)


def test_graph_run_is_deviceless_capable(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("No device", graph={
        "version": 1,
        "nodes": [{"id": "t", "type": "manual-trigger", "config": {}}],
        "edges": [], "meta": {},
    })
    run = app.enqueue_run(a["id"], device_id=None, trigger_type="manual")
    _drain(JobConsumer())
    assert app.get_automation_run(run["id"])["status"] == "completed"


def test_enqueue_run_funnels_linear_automations_too(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Linear", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])
    run = app.enqueue_run(a["id"], device_id="serial-1")
    assert run["kind"] == "linear" if "kind" in run else True
    assert app.list_jobs(kind="automation.run")
    _drain(JobConsumer())
    assert app.get_automation_run(run["id"])["status"] == "completed"


def test_cancel_queued_graph_run(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Graph flow", graph=_graph_doc())
    run = app.execute_automation(a["id"], "serial-1")

    assert app.cancel_automation_run(run["id"]) is True
    assert app.get_automation_run(run["id"])["status"] == "cancelled"
    _drain(JobConsumer())
    assert app.get_automation_run(run["id"])["status"] == "cancelled"


def test_failed_trigger_payload_recorded(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Graph flow", graph=_graph_doc())
    run = app.enqueue_run(a["id"], device_id="serial-1",
                          trigger_type="webhook", trigger={"body": {"x": 1}})
    got = app.get_automation_run(run["id"])
    assert got["trigger"] == {"type": "webhook", "payload": {"body": {"x": 1}}}


def test_save_graph_validates_and_clears_shim_flag(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Editable", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])

    derived = app.get_automation_graph(a["id"])
    assert derived["derived"] is True
    assert derived["graph"]["meta"]["shim"] is True

    doc = derived["graph"]
    saved = app.save_automation_graph(a["id"], doc)
    assert saved["graph"]["meta"].get("shim") is None
    assert app.get_automation_graph(a["id"])["derived"] is False

    # Invalid docs are rejected before storage.
    bad = dict(doc, edges=doc["edges"] + [
        {"id": "loop", "source": doc["nodes"][-1]["id"], "target": doc["nodes"][0]["id"]}])
    with pytest.raises(ValueError):
        app.save_automation_graph(a["id"], bad)


def test_graph_survives_clone_export_import(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Graph flow", graph=_graph_doc())

    clone = app.clone_automation(a["id"])
    assert clone["graph"]["nodes"] == _graph_doc()["nodes"]

    exported = app.export_automation(a["id"])
    assert "webhook_token" not in exported
    imported = app.import_automation(exported)
    assert imported["graph"]["edges"] == _graph_doc()["edges"]
