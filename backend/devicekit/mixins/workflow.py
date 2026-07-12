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
from devicekit.jobs.service import JobService
from devicekit.models import Automation, AutomationRun
from devicekit.workflow import WorkflowEngine, linear_steps_to_doc, validate_doc
from devicekit.workflow.doc import is_workflow_doc

logger = logging.getLogger(__name__)


class WorkflowMixin:

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
        return self.execute_automation(automation_id, device_id, self_heal=self_heal)

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
