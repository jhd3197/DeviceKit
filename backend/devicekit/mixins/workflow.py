"""WorkflowMixin — graph automations (plan 22): WorkflowDoc storage, validation, and
the graph run path.

The stored doc is tramo's ``WorkflowDoc``; execution is the Python engine in
``devicekit/workflow``. Linear automations are untouched — an automation with no
``graph`` runs through the existing step loop, and the compat shim renders its steps
as a straight-line doc for the editor without storing anything.

``enqueue_run`` is the single funnel every trigger goes through (plan 22 part 4):
manual today; webhook / cron / event call the same method with their trigger payload.
"""
import logging
import threading
import time
import uuid

from devicekit.db import session_scope
from devicekit.jobs.service import JobService, ScheduledJobService
from devicekit.models import Automation, AutomationRun
from devicekit.workflow import (
    WorkflowEngine, build_node_pack, linear_steps_to_doc, validate_doc,
)
from devicekit.workflow.doc import is_workflow_doc

logger = logging.getLogger(__name__)

#: Headers never forwarded into {{trigger.headers.*}} — credential-bearing.
_WEBHOOK_HEADER_DENYLIST = {
    "authorization", "cookie", "x-api-key", "x-session-token", "x-agent-token",
}

#: Default seconds between event-triggered runs of the same automation (storm guard).
EVENT_TRIGGER_COOLDOWN = 60


class WorkflowMixin:
    _event_trigger_index_cache = None   # event_key -> [automation ids]; None = dirty
    _event_trigger_last = {}            # automation_id -> last event-run timestamp

    # ------------------------------------------------------------------
    # Graph storage + validation
    # ------------------------------------------------------------------
    def get_automation_graph(self, automation_id):
        """The stored WorkflowDoc, or a shim derived from the linear steps.

        Returns ``{'graph': doc, 'derived': bool}`` — ``derived`` tells the editor
        it is looking at an unsaved projection of a linear automation."""
        automation = self.get_automation(automation_id)
        if not automation:
            return None
        graph = automation.get("graph")
        if is_workflow_doc(graph):
            return {"graph": graph, "derived": False}
        return {"graph": linear_steps_to_doc(automation), "derived": True}

    def get_node_pack(self):
        """tramo NodeDefinitions for every registered step type (core + extensions),
        plus the list of tramo builtins the Python engine executes. The editor folds
        this into its registry next to ``BUILTIN_NODES`` (plan 22 part 2)."""
        event_keys = None
        if hasattr(self, "list_notification_events"):
            try:
                event_keys = [e["event_key"] for e in self.list_notification_events()]
            except Exception:
                event_keys = None
        return build_node_pack(self.get_step_types(), event_keys=event_keys)

    def validate_workflow_doc(self, doc):
        """Structural + Kahn validation (the backend authority behind
        ``POST /automations/<id>/validate``); mirrors ``@tramo/spec`` ``topoSort``."""
        return validate_doc(doc)

    def save_automation_graph(self, automation_id, doc):
        """Validate and store a WorkflowDoc on the automation. Raises ``ValueError``
        on an invalid doc; returns the updated automation dict."""
        check = validate_doc(doc)
        if not check["ok"]:
            raise ValueError("; ".join(check["errors"]))
        meta = doc.get("meta")
        if isinstance(meta, dict):
            meta.pop("shim", None)   # a saved doc is authoritative, not derived
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            if not automation:
                return None
            automation.graph = doc
            automation.updated_at = time.time()
            s.flush()
            result = automation.to_dict()
        self.sync_automation_triggers(automation_id, doc)
        logger.info(f"Saved workflow graph for automation {automation_id} "
                    f"({len(doc.get('nodes', []))} nodes)")
        return result

    # ------------------------------------------------------------------
    # Run funnel — all four trigger types converge here (plan 22 part 4)
    # ------------------------------------------------------------------
    def enqueue_run(self, automation_id, device_id=None, trigger_type="manual",
                    trigger=None, self_heal=False):
        """Create a run for an automation and enqueue its job. Graph automations run
        on the workflow engine; linear ones fall through to ``execute_automation``."""
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")
        if is_workflow_doc(automation.get("graph")):
            return self._enqueue_graph_run(automation, device_id, trigger_type,
                                           trigger, self_heal=self_heal)
        return self.execute_automation(automation_id, device_id, self_heal=self_heal,
                                       trigger_type=trigger_type, trigger=trigger)

    def _enqueue_graph_run(self, automation, device_id, trigger_type, trigger,
                           self_heal=False):
        doc = automation["graph"]
        trigger_record = {"type": trigger_type}
        if trigger is not None:
            trigger_record["payload"] = trigger
        run_record = {
            "id": str(uuid.uuid4()),
            "automation_id": automation["id"],
            "automation_name": automation.get("name", ""),
            "device_id": device_id,
            "status": "queued",
            "started_at": time.time(),
            "finished_at": None,
            "total_steps": len(doc.get("nodes", [])),
            "completed_steps": 0,
            "current_step_index": 0,
            "step_results": [],
            "error": None,
            "self_heal": self_heal,
            "kind": "graph",
            "trigger": trigger_record,
        }
        self._save_run(run_record)

        # The doc snapshot rides the payload so an edit between enqueue and execution
        # doesn't change what this run does (same contract as linear runs).
        job = JobService.enqueue(
            "automation.run_graph",
            payload={
                "run_id": run_record["id"],
                "automation_id": automation["id"],
                "device_id": device_id,
                "graph": doc,
                "trigger": trigger_record,
            },
            max_attempts=1,
            owner_type="automation_run",
            owner_id=run_record["id"],
        )
        self._run_jobs[run_record["id"]] = job["id"]
        return run_record

    # ------------------------------------------------------------------
    # Job handler — automation.run_graph (registered by JobsMixin)
    # ------------------------------------------------------------------
    def _job_run_graph(self, job):
        payload = job.get("payload", {})
        run_id = payload.get("run_id")
        device_id = payload.get("device_id")
        doc = payload.get("graph") or {}
        trigger_record = payload.get("trigger") or {"type": "manual"}
        if not run_id:
            return {"error": "missing run_id"}

        run_record = self.get_automation_run(run_id)
        if not run_record:
            return {"skipped": "run record missing"}
        if run_record.get("status") in ("cancelled", "failed", "completed"):
            return {"skipped": run_record.get("status")}

        cancel_event = threading.Event()
        self._active_runs[run_id] = cancel_event

        try:
            if device_id:
                lock = self._device_run_lock(device_id)
                with lock:
                    result = self._run_graph(run_record, doc, device_id,
                                             trigger_record, cancel_event)
            else:
                result = self._run_graph(run_record, doc, None,
                                         trigger_record, cancel_event)
        except Exception as e:
            logger.error(f"Graph run {run_id} crashed: {e}")
            run_record.update({"status": "failed", "finished_at": time.time(),
                               "error": str(e)})
            self._save_run(run_record)
            self._notify_run_failed(run_record, run_record.get("current_step_index", 0),
                                    None, str(e))
            result = {"run_id": run_id, "status": "failed"}
        finally:
            self._active_runs.pop(run_id, None)
            self._run_jobs.pop(run_id, None)
        return result

    def _run_graph(self, run_record, doc, device_id, trigger_record, cancel_event):
        run_id = run_record["id"]
        if cancel_event.is_set():
            run_record.update({"status": "cancelled", "finished_at": time.time()})
            self._save_run(run_record)
            return {"run_id": run_id, "status": "cancelled"}

        run_record["status"] = "running"
        self._save_run(run_record)

        engine = WorkflowEngine(
            self, doc,
            device_id=device_id,
            trigger=trigger_record.get("payload") or {},
            cancel_event=cancel_event,
            run_id=run_id,
            # Seed the cross-automation cycle guard: call-flow / device-fan-out nodes
            # reject anything already on the stack, starting with this automation.
            call_stack=[run_record.get("automation_id")],
        )

        def on_event(event):
            # Mirrors tramo's RunEvent shapes so the editor's deriveRunState can
            # consume the stream unchanged (plan 22 phase 6 live run view).
            if hasattr(self, "broadcast"):
                try:
                    self.broadcast("automation_run", {"run_id": run_id, **event})
                except Exception:
                    pass

        def on_node_update(_record):
            records = [engine.records[nid] for nid in
                       (n["id"] for n in doc.get("nodes", []))
                       if nid in engine.records]
            terminal = [r for r in records if r["status"] in
                        ("completed", "failed", "skipped")]
            run_record["step_results"] = records
            run_record["completed_steps"] = sum(
                1 for r in records if r["status"] == "completed")
            run_record["current_step_index"] = len(terminal)
            self._save_run(run_record)

        engine.on_event = on_event
        engine.on_node_update = on_node_update

        result = engine.run()

        run_record.update({
            "status": result["status"],
            "finished_at": time.time(),
            "error": result["error"],
            "step_results": result["records"],
            "completed_steps": sum(1 for r in result["records"]
                                   if r["status"] == "completed"),
            "current_step_index": len(result["records"]),
        })
        self._save_run(run_record)
        if result["status"] == "failed":
            failed = next((r for r in result["records"] if r["status"] == "failed"), None)
            self._notify_run_failed(
                run_record,
                result["records"].index(failed) if failed else 0,
                {"type": (failed or {}).get("step_type", "")} if failed else None,
                result["error"] or "")
        return {"run_id": run_id, "status": result["status"],
                "completed_steps": run_record["completed_steps"]}

    # ------------------------------------------------------------------
    # Trigger sync — the doc's trigger nodes materialize as real trigger
    # infrastructure (plan 22 part 4): webhook token, cron schedule, event index.
    # ------------------------------------------------------------------
    @staticmethod
    def _find_trigger_nodes(doc, node_type):
        return [n for n in (doc or {}).get("nodes", []) if n.get("type") == node_type]

    def sync_automation_triggers(self, automation_id, doc):
        """Reconcile trigger infrastructure with the saved doc: ensure/remove the cron
        ScheduledJob and the webhook token, and invalidate the event-trigger index."""
        # Cron — one plan-05 schedule per automation, keyed by name.
        schedule_name = f"automation.cron.{automation_id}"
        cron_nodes = self._find_trigger_nodes(doc, "cron-trigger")
        if cron_nodes:
            config = cron_nodes[0].get("config") or {}
            expression = str(config.get("expression") or "").strip()
            if expression:
                ScheduledJobService.ensure(
                    schedule_name, "automation.trigger.cron",
                    cron=expression,
                    payload={"automation_id": automation_id,
                             "device_id": config.get("device_id")},
                    owner_type="automation", owner_id=automation_id)
            else:
                ScheduledJobService.delete_by_name(schedule_name)
        else:
            ScheduledJobService.delete_by_name(schedule_name)

        # Webhook — mint the token as soon as the doc declares the trigger, so the
        # editor can show the URL immediately.
        if self._find_trigger_nodes(doc, "webhook-trigger"):
            self.ensure_webhook_token(automation_id)

        WorkflowMixin._event_trigger_index_cache = None

    def _cleanup_automation_triggers(self, automation_id):
        """Called by delete_automation — drop the cron schedule + index entry."""
        try:
            ScheduledJobService.delete_by_name(f"automation.cron.{automation_id}")
        except Exception:
            pass
        WorkflowMixin._event_trigger_index_cache = None

    # ------------------------------------------------------------------
    # Webhook trigger — POST /hooks/<token>; the token *is* the auth
    # ------------------------------------------------------------------
    def ensure_webhook_token(self, automation_id, rotate=False):
        """Create (or rotate) the automation's inbound webhook token. Returns the
        token string, or None if the automation doesn't exist."""
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            if not automation:
                return None
            if rotate or not automation.webhook_token:
                automation.webhook_token = uuid.uuid4().hex
            return automation.webhook_token

    def get_webhook_token(self, automation_id):
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            return automation.webhook_token if automation else None

    def revoke_webhook_token(self, automation_id):
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            if not automation:
                return False
            automation.webhook_token = None
        return True

    def handle_webhook_trigger(self, token, body=None, query=None, headers=None):
        """The ``POST /hooks/<token>`` handler: resolve the automation by token and
        enqueue a run with the request wrapped as ``{{trigger.*}}``. Raises
        ``LookupError`` on an unknown token (the route turns it into a 404)."""
        with session_scope() as s:
            row = (s.query(Automation)
                   .filter(Automation.webhook_token == token)
                   .first())
            automation_id = row.id if row else None
        if not automation_id:
            raise LookupError("Unknown webhook token")
        safe_headers = {k: v for k, v in (headers or {}).items()
                        if k.lower() not in _WEBHOOK_HEADER_DENYLIST}
        payload = {"body": body, "query": dict(query or {}), "headers": safe_headers}
        device_id = None
        if isinstance(body, dict) and body.get("device_id"):
            device_id = body["device_id"]
        elif (query or {}).get("device_id"):
            device_id = query["device_id"]
        return self.enqueue_run(automation_id, device_id=device_id,
                                trigger_type="webhook", trigger=payload)

    # ------------------------------------------------------------------
    # Cron trigger — plan-05 ScheduledJob fires automation.trigger.cron
    # ------------------------------------------------------------------
    def _job_trigger_cron(self, job):
        payload = job.get("payload", {})
        automation_id = payload.get("automation_id")
        if not automation_id:
            return {"error": "missing automation_id"}
        automation = self.get_automation(automation_id)
        if not automation:
            # The automation vanished — drop the orphaned schedule.
            ScheduledJobService.delete_by_name(f"automation.cron.{automation_id}")
            return {"skipped": "automation deleted"}
        run = self.enqueue_run(automation_id, device_id=payload.get("device_id"),
                               trigger_type="cron", trigger={"firedAt": time.time()})
        return {"run_id": run["id"]}

    # ------------------------------------------------------------------
    # Event trigger — plan-06 bus events start runs (dk.event-trigger nodes)
    # ------------------------------------------------------------------
    def _event_trigger_index(self):
        """``event_key → [(automation_id, cooldown_seconds, device_from_event)]`` for
        every automation whose graph has a ``dk.event-trigger`` node. Cached until a
        graph save/delete invalidates it (single-process, cheap to rebuild)."""
        cached = WorkflowMixin._event_trigger_index_cache
        if cached is not None:
            return cached
        index = {}
        with session_scope() as s:
            rows = s.query(Automation.id, Automation.graph).filter(
                Automation.graph.isnot(None)).all()
        for automation_id, graph in rows:
            for node in self._find_trigger_nodes(graph or {}, "dk.event-trigger"):
                config = node.get("config") or {}
                event_key = str(config.get("event_key") or "").strip()
                if not event_key:
                    continue
                try:
                    cooldown = float(config.get("cooldown_seconds")
                                     or EVENT_TRIGGER_COOLDOWN)
                except (TypeError, ValueError):
                    cooldown = EVENT_TRIGGER_COOLDOWN
                index.setdefault(event_key, []).append((automation_id, cooldown))
        WorkflowMixin._event_trigger_index_cache = index
        return index

    def dispatch_event_triggers(self, event_key, data):
        """Called by ``notify_event`` for every bus event. When any automation is
        wired to this event, enqueue one ``automation.dispatch`` job (the matching +
        cooldown happens there, off the caller's thread). No-op otherwise."""
        if event_key not in self._event_trigger_index():
            return None
        return JobService.enqueue(
            "automation.dispatch",
            payload={"event_key": event_key, "data": data},
            max_attempts=1, owner_type="event_trigger", owner_id=event_key)

    def _job_dispatch_event(self, job):
        """Job handler for ``automation.dispatch`` — start every event-triggered
        automation matching the event, honoring each one's cooldown."""
        payload = job.get("payload", {})
        event_key = payload.get("event_key") or ""
        data = payload.get("data") or {}
        entries = self._event_trigger_index().get(event_key, [])
        now = time.time()
        fired, cooled = [], 0
        for automation_id, cooldown in entries:
            last = WorkflowMixin._event_trigger_last.get(automation_id, 0)
            if now - last < cooldown:
                cooled += 1
                continue
            try:
                run = self.enqueue_run(
                    automation_id,
                    device_id=data.get("device_id"),
                    trigger_type="event",
                    trigger={"event": event_key, "data": data})
                WorkflowMixin._event_trigger_last[automation_id] = now
                fired.append(run["id"])
            except Exception as e:
                logger.warning("Event trigger for %s failed: %s", automation_id, e)
        return {"event": event_key, "fired": fired, "cooldown_skipped": cooled}
