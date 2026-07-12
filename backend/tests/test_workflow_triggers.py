"""Plan 22 phase 4: all four trigger types funnel through one ``enqueue_run`` —
manual (existing), webhook (``POST /hooks/<token>``, token is auth), cron (plan-05
ScheduledJob), and event (plan-06 bus → ``automation.dispatch`` with per-automation
cooldown).
"""
import pytest

from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.notifications import NotificationsMixin
from devicekit.mixins.workflow import WorkflowMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.jobs import registry
from devicekit.jobs.service import GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG, ScheduledJobService
from devicekit.jobs.consumer import JobConsumer
from devicekit.queue_bus.service import QueueBusService
from devicekit.services.gate import authorize


class _App(AutomationMixin, WorkflowMixin, JobsMixin, NotificationsMixin):
    def __init__(self):
        self.events = []

    def broadcast(self, event_type, data):
        self.events.append((event_type, data))


@pytest.fixture(autouse=True)
def _clean_state():
    registry.clear()
    WorkflowMixin._event_trigger_index_cache = None
    WorkflowMixin._event_trigger_last = {}
    yield
    registry.clear()
    WorkflowMixin._event_trigger_index_cache = None
    WorkflowMixin._event_trigger_last = {}


def _graph(trigger_node):
    return {
        "version": 1,
        "nodes": [trigger_node,
                  {"id": "w", "type": "dk.wait", "label": "w", "config": {"delay": 1}}],
        "edges": [{"id": "e1", "source": trigger_node["id"], "target": "w"}],
        "meta": {},
    }


def _drain(consumer=None):
    consumer = consumer or JobConsumer()
    msgs = QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"], max_messages=20)
    for m in msgs:
        consumer.process_message(m)
    return len(msgs)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def test_saving_webhook_trigger_graph_mints_token(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Hooked")
    app.save_automation_graph(a["id"], _graph(
        {"id": "wh", "type": "webhook-trigger", "config": {}}))
    token = app.get_webhook_token(a["id"])
    assert token and len(token) == 32
    # The token never rides list/detail payloads — presence only.
    detail = app.get_automation(a["id"])
    assert "webhook_token" not in detail
    assert detail["has_webhook"] is True


def test_webhook_trigger_starts_run_with_wrapped_request(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Hooked", graph=_graph(
        {"id": "wh", "type": "webhook-trigger", "config": {}}))
    token = app.ensure_webhook_token(a["id"])

    run = app.handle_webhook_trigger(
        token,
        body={"device_id": "serial-9", "action": "sync"},
        query={"source": "github"},
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer secret",
                 "Cookie": "sid=1", "X-GitHub-Event": "push"})
    assert run["kind"] == "graph"
    assert run["device_id"] == "serial-9"
    trig = run["trigger"]
    assert trig["type"] == "webhook"
    assert trig["payload"]["body"]["action"] == "sync"
    assert trig["payload"]["query"] == {"source": "github"}
    headers = trig["payload"]["headers"]
    assert "Authorization" not in headers and "Cookie" not in headers
    assert headers.get("X-GitHub-Event") == "push"

    _drain()
    assert app.get_automation_run(run["id"])["status"] == "completed"


def test_unknown_or_revoked_webhook_token_404s(fresh_db):
    app = _App()
    app.init_jobs()
    with pytest.raises(LookupError):
        app.handle_webhook_trigger("nope", body={})

    a = app.create_automation("Hooked", graph=_graph(
        {"id": "wh", "type": "webhook-trigger", "config": {}}))
    token = app.ensure_webhook_token(a["id"])
    assert app.revoke_webhook_token(a["id"]) is True
    with pytest.raises(LookupError):
        app.handle_webhook_trigger(token, body={})


def test_rotate_webhook_token(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Hooked")
    first = app.ensure_webhook_token(a["id"])
    assert app.ensure_webhook_token(a["id"]) == first          # idempotent
    rotated = app.ensure_webhook_token(a["id"], rotate=True)
    assert rotated != first


def test_hooks_path_is_public_in_the_gate():
    class _Req:
        path = "/hooks/abc123"
        method = "POST"

    class _Client:
        def anonymous_principal(self):
            return "anon"

    principal, error = authorize(_Client(), _Req())
    assert principal == "anon" and error is None
    # The /api/v1 mirror authorizes identically.
    _Req.path = "/api/v1/hooks/abc123"
    principal, error = authorize(_Client(), _Req())
    assert error is None


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------

def test_cron_trigger_node_syncs_scheduled_job(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Nightly")
    doc = _graph({"id": "cr", "type": "cron-trigger",
                  "config": {"expression": "*/5 * * * *", "device_id": "serial-1"}})
    app.save_automation_graph(a["id"], doc)

    schedules = ScheduledJobService.list(owner_type="automation", owner_id=a["id"])
    assert len(schedules) == 1
    sch = schedules[0]
    assert sch["kind"] == "automation.trigger.cron"
    assert sch["cron"] == "*/5 * * * *"

    # Removing the trigger node removes the schedule.
    doc_no_cron = _graph({"id": "m", "type": "manual-trigger", "config": {}})
    app.save_automation_graph(a["id"], doc_no_cron)
    assert ScheduledJobService.list(owner_type="automation", owner_id=a["id"]) == []


def test_cron_job_handler_enqueues_run(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Nightly", graph=_graph(
        {"id": "cr", "type": "cron-trigger", "config": {"expression": "*/5 * * * *"}}))

    result = app._job_trigger_cron({"payload": {"automation_id": a["id"],
                                                "device_id": "serial-1"}})
    run = app.get_automation_run(result["run_id"])
    assert run["trigger"]["type"] == "cron"
    assert run["device_id"] == "serial-1"
    _drain()
    assert app.get_automation_run(run["id"])["status"] == "completed"


def test_cron_handler_prunes_orphaned_schedule(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("Nightly", graph=_graph(
        {"id": "cr", "type": "cron-trigger", "config": {"expression": "*/5 * * * *"}}))
    assert ScheduledJobService.list(owner_type="automation", owner_id=a["id"])

    app.delete_automation(a["id"])
    # delete_automation already cleaned the schedule…
    assert ScheduledJobService.list(owner_type="automation", owner_id=a["id"]) == []
    # …and a straggler tick self-prunes instead of crashing.
    result = app._job_trigger_cron({"payload": {"automation_id": a["id"]}})
    assert result == {"skipped": "automation deleted"}


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

def _event_graph(event_key="device.offline", cooldown=0):
    return _graph({"id": "ev", "type": "dk.event-trigger",
                   "config": {"event_key": event_key,
                              "cooldown_seconds": cooldown}})


def test_bus_event_starts_matching_automation(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("On offline", graph=_event_graph())

    # The producer hook: notify_event → dispatch_event_triggers → automation.dispatch.
    app.notify_event("device.offline", data={"device_id": "serial-2", "name": "Moto"})
    assert app.list_jobs(kind="automation.dispatch")

    _drain()   # dispatch job matches + enqueues the run; run job executes
    _drain()
    runs = app.list_automation_runs(automation_id=a["id"])
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "completed"
    assert run["trigger"]["type"] == "event"
    assert run["trigger"]["payload"]["event"] == "device.offline"
    assert run["device_id"] == "serial-2"


def test_event_dispatch_noops_without_matching_automations(fresh_db):
    app = _App()
    app.init_jobs()
    app.create_automation("Unrelated", graph=_graph(
        {"id": "m", "type": "manual-trigger", "config": {}}))
    assert app.dispatch_event_triggers("device.offline", {}) is None
    assert app.list_jobs(kind="automation.dispatch") == []


def test_event_trigger_cooldown_prevents_storms(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("On offline", graph=_event_graph(cooldown=3600))

    first = app._job_dispatch_event({"payload": {"event_key": "device.offline",
                                                 "data": {}}})
    assert len(first["fired"]) == 1
    second = app._job_dispatch_event({"payload": {"event_key": "device.offline",
                                                  "data": {}}})
    assert second["fired"] == [] and second["cooldown_skipped"] == 1
    assert len(app.list_automation_runs(automation_id=a["id"])) == 1


def test_event_index_invalidates_on_graph_change(fresh_db):
    app = _App()
    app.init_jobs()
    a = app.create_automation("On offline", graph=_event_graph())
    assert "device.offline" in app._event_trigger_index()

    app.save_automation_graph(a["id"], _graph(
        {"id": "m", "type": "manual-trigger", "config": {}}))
    assert "device.offline" not in app._event_trigger_index()


# ---------------------------------------------------------------------------
# Node pack exposes the event trigger
# ---------------------------------------------------------------------------

def test_node_pack_includes_event_trigger(fresh_db):
    app = _App()
    pack = app.get_node_pack()
    ev = next(n for n in pack["nodes"] if n["id"] == "dk.event-trigger")
    assert ev["category"] == "trigger"
    assert ev["outputs"] == [{"key": "out", "label": "Event", "type": "object"}]
    assert "dk.event-trigger" in pack["supported_builtins"]
