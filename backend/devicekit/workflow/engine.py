"""The WorkflowDoc executor — a Python port of tramo's runner (``runner.ts``).

Executes a validated doc as a sequential topological walk (concurrency=1 in tramo
terms — real device fan-out happens as *jobs* on the plan-05 queue, never inline
threads). Ported semantics, kept in sync with the TS reference:

- **Port routing / branch gate:** each edge reads ``sourceHandle`` (default ``out``)
  from the upstream node's port-map result. A port the upstream didn't emit skips the
  downstream node under ``on-success`` — this is the entire branching mechanism (an
  ``if`` emits ``{yes: …}`` *or* ``{no: …}``).
- **runAfter gating:** ``on-success`` (default) needs every predecessor un-skipped and
  un-errored; ``on-error`` needs at least one errored predecessor; ``always`` runs
  regardless (missing inputs arrive as ``None``).
- **Retry:** an executor that *raises* retries per the node's ``RetryPolicy``
  (``{count, delayMs, backoff, maxDelayMs, jitter}``). Returning an ``{'error': …}``
  envelope is a normal success and is never retried.
- **steps map:** completed outputs keyed by node id *and* slug; single-port ``{out}``
  results flatten to the bare value.

DeviceKit extensions on top of the reference:

- ``critical`` config flag — a failed node with ``critical: true`` aborts the whole run
  (ServerKit's ``{success, critical}`` contract; the linear→graph shim sets it so old
  automations keep abort-on-failure behavior). Non-critical failures flow through
  ``runAfter`` like tramo.
- Run status: ``failed`` when aborted or when any errored node has no successful
  ``on-error``/``always`` successor (a compensation branch that ran counts as handling
  the error); ``completed`` otherwise.
- Events mirror tramo's ``RunEvent`` shapes so the editor's ``deriveRunState`` consumes
  them unchanged for live run visualization.
"""
import logging
import random
import threading
import time

from devicekit.workflow.doc import (
    topo_sort, validate_doc, build_step_slug_map, incoming_edges, SPEC_VERSION,
)
from devicekit.workflow.executors import resolve_executor

logger = logging.getLogger(__name__)

#: Hard ceiling on sub-flow nesting (call-flow recursion guard).
MAX_CALL_DEPTH = 8


class WorkflowAborted(Exception):
    """Raised internally when a critical node failure aborts the walk."""


class WorkflowEngine:

    def __init__(self, client, doc, device_id=None, trigger=None, cancel_event=None,
                 on_event=None, on_node_update=None, run_id=None, depth=0,
                 call_stack=None):
        self.client = client
        self.doc = doc
        self.device_id = device_id
        self.trigger = trigger if trigger is not None else {}
        self.cancel_event = cancel_event or threading.Event()
        self.on_event = on_event
        self.on_node_update = on_node_update
        self.run_id = run_id or ""
        self.depth = depth
        #: Automation ids currently on the call-flow stack (cross-automation cycle guard).
        self.call_stack = list(call_stack or [])

        self.vars = {}
        self.steps = {}          # id + slug → step value (tramo `steps` map)
        self.node_results = {}   # id → normalized port map
        self.errored = set()
        self.skipped = {}        # id → reason
        self.records = {}        # id → per-node record dict (run persistence shape)
        _, self.id_to_slug = build_step_slug_map(doc)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _emit(self, event):
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    def _record(self, node, **updates):
        rec = self.records.get(node["id"])
        if rec is None:
            rec = {
                "step_id": node["id"],
                "node_id": node["id"],
                "step_type": node.get("type", "unknown"),
                "label": node.get("label", "") or node.get("type", ""),
                "slug": self.id_to_slug.get(node["id"], node["id"]),
                "status": "pending",
                "output": None,
                "error": None,
                "duration_ms": 0,
                "attempts": 0,
            }
            self.records[node["id"]] = rec
        rec.update(updates)
        if self.on_node_update:
            try:
                self.on_node_update(rec)
            except Exception:
                pass
        return rec

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self):
        if self.doc.get("version") != SPEC_VERSION:
            err = (f"Workflow spec version {self.doc.get('version')!r} is not supported "
                   f"(expects {SPEC_VERSION}).")
            self._emit({"type": "run-end", "runId": self.run_id, "ok": False, "error": err})
            return self._result(ok=False, status="failed", error=err)

        check = validate_doc(self.doc)
        if not check["ok"]:
            err = "; ".join(check["errors"])
            self._emit({"type": "run-end", "runId": self.run_id, "ok": False, "error": err})
            return self._result(ok=False, status="failed", error=err)

        topo = topo_sort(self.doc)
        order = topo["order"]
        self._emit({"type": "run-start", "runId": self.run_id, "nodeOrder": order})

        nodes_by_id = {n["id"]: n for n in self.doc.get("nodes", [])}
        aborted_by = None
        cancelled = False

        for node_id in order:
            node = nodes_by_id[node_id]
            if self.cancel_event.is_set():
                cancelled = True
                self._skip(node, "run cancelled")
                continue
            if aborted_by:
                self._skip(node, f"aborted by critical failure of '{aborted_by}'")
                continue
            try:
                self._execute_node(node)
            except WorkflowAborted:
                aborted_by = self.id_to_slug.get(node_id, node_id)

        if cancelled:
            self._emit({"type": "run-end", "runId": self.run_id, "ok": False,
                        "error": "cancelled"})
            return self._result(ok=False, status="cancelled", error=None)

        error = None
        unhandled = self._unhandled_errors()
        if aborted_by:
            failed_rec = next((r for r in self.records.values()
                               if r["status"] == "failed"), None)
            error = (failed_rec or {}).get("error") or f"critical node '{aborted_by}' failed"
            status = "failed"
        elif unhandled:
            slugs = [self.id_to_slug.get(nid, nid) for nid in unhandled]
            first = self.records.get(unhandled[0], {})
            error = (f"{len(unhandled)} node(s) failed without an error branch: "
                     f"{', '.join(slugs[:5])}"
                     + (f" — {first.get('error')}" if first.get("error") else ""))
            status = "failed"
        else:
            status = "completed"

        self._emit({"type": "run-end", "runId": self.run_id,
                    "ok": status == "completed", "error": error})
        return self._result(ok=status == "completed", status=status, error=error)

    def _result(self, ok, status, error):
        return {
            "ok": ok,
            "status": status,
            "error": error,
            "node_results": self.node_results,
            "records": [self.records[nid] for nid in
                        (n["id"] for n in self.doc.get("nodes", []))
                        if nid in self.records],
            "vars": self.vars,
        }

    def _unhandled_errors(self):
        """Errored nodes with no successful ``on-error``/``always`` successor.

        A compensation branch that actually ran counts as handling the failure; a
        bare error fails the run so it can't rot silently."""
        unhandled = []
        edges = self.doc.get("edges", [])
        nodes_by_id = {n["id"]: n for n in self.doc.get("nodes", [])}
        for nid in self.errored:
            handled = False
            for e in edges:
                if e.get("source") != nid:
                    continue
                succ = nodes_by_id.get(e.get("target"))
                if not succ:
                    continue
                if succ.get("runAfter") in ("on-error", "always") and \
                        self.records.get(succ["id"], {}).get("status") == "completed":
                    handled = True
                    break
            if not handled:
                unhandled.append(nid)
        return unhandled

    # ------------------------------------------------------------------
    # Node execution (port of runner.ts executeNode)
    # ------------------------------------------------------------------
    def _skip(self, node, reason):
        self.skipped[node["id"]] = reason
        self._record(node, status="skipped", error=None, output=reason)
        self._emit({"type": "node-skip", "runId": self.run_id,
                    "nodeId": node["id"], "reason": reason})

    def _execute_node(self, node):
        node_id = node["id"]
        executor = resolve_executor(self, node)
        if executor is None:
            self._skip(node, f"No executor for node type '{node.get('type')}'")
            return

        run_after = node.get("runAfter") or "on-success"
        edges = incoming_edges(self.doc, node_id)
        upstream_error = any(e.get("source") in self.errored for e in edges)
        all_succeeded = all(e.get("source") not in self.skipped for e in edges)

        if run_after == "on-success" and not all_succeeded:
            which = "upstream errored" if upstream_error else "upstream skipped"
            self._skip(node, f"{which} (runAfter=on-success)")
            return
        if run_after == "on-error" and not upstream_error:
            self._skip(node, "no upstream errored (runAfter=on-error)")
            return

        # Gather inputs along edges — the branch gate lives here.
        inputs = {}
        for edge in edges:
            from_port = edge.get("sourceHandle") or "out"
            to_port = edge.get("targetHandle") or "in"
            source = edge.get("source")
            if source in self.skipped:
                if run_after == "on-success":
                    self._skip(node, f"upstream {source} skipped ({self.skipped[source]})")
                    return
                inputs[to_port] = None
                continue
            upstream = self.node_results.get(source)
            if isinstance(upstream, dict) and from_port in upstream:
                value = upstream[from_port]
            elif from_port == "out" and upstream is None:
                # Upstream emitted nothing at all — an undefined input, not a gate.
                value = None
            elif run_after == "on-success":
                # The upstream emitted a *different* port (e.g. `{error}` while this
                # edge reads `out`) — the branch gate. Note: tramo's runner originally
                # passed the whole result through for `out` here; fixed at source to
                # match this gating (error envelopes must not leak into happy paths).
                self._skip(node, f"upstream {source} did not emit port \"{from_port}\"")
                return
            else:
                value = None
            inputs[to_port] = value

        if not edges:
            inputs["in"] = self.trigger

        self._record(node, status="running")
        self._emit({"type": "node-start", "runId": self.run_id, "nodeId": node_id})
        start = time.time()

        retry = node.get("retry") or {}
        max_attempts = 1 + max(0, int(retry.get("count") or 0))
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            if self.cancel_event.is_set():
                break
            try:
                result = executor(self, node, inputs)
                normalized = _normalize_result(result)
                self.node_results[node_id] = normalized
                self._record_step_value(node_id, normalized)
                duration_ms = int((time.time() - start) * 1000)
                self._record(node, status="completed", duration_ms=duration_ms,
                             attempts=attempt, output=_summarize_output(normalized))
                self._emit({"type": "node-success", "runId": self.run_id,
                            "nodeId": node_id, "output": normalized,
                            "durationMs": duration_ms})
                return
            except WorkflowAborted:
                raise
            except Exception as e:
                last_error = str(e) or type(e).__name__
                if attempt < max_attempts and not self.cancel_event.is_set():
                    delay_ms = _compute_backoff(retry, attempt)
                    self._emit({"type": "node-log", "runId": self.run_id,
                                "nodeId": node_id, "level": "warn",
                                "message": f"attempt {attempt}/{max_attempts} failed: "
                                           f"{last_error} — retrying in {delay_ms}ms"})
                    if delay_ms and self.cancel_event.wait(delay_ms / 1000.0):
                        break  # cancelled during backoff

        duration_ms = int((time.time() - start) * 1000)
        self.errored.add(node_id)
        self.skipped[node_id] = f"error: {last_error}"
        self._record(node, status="failed", error=last_error,
                     duration_ms=duration_ms, attempts=max_attempts)
        self._emit({"type": "node-error", "runId": self.run_id, "nodeId": node_id,
                    "error": last_error, "durationMs": duration_ms})
        logger.warning("Workflow node %s failed after %d attempt(s): %s",
                       node_id, max_attempts, last_error)
        if _is_critical(node):
            raise WorkflowAborted(last_error)

    def _record_step_value(self, node_id, normalized):
        value = _step_value(normalized)
        self.steps[node_id] = value
        slug = self.id_to_slug.get(node_id)
        if slug:
            self.steps[slug] = value

    # ------------------------------------------------------------------
    # Shared context helpers used by executors
    # ------------------------------------------------------------------
    def expr_env(self, inputs, node=None, extra=None):
        env = {
            "input": inputs.get("in"),
            "vars": self.vars,
            "steps": self.steps,
            "trigger": self.trigger,
            "config": (node or {}).get("config") or {},
        }
        if extra:
            env.update(extra)
        return env


def _is_critical(node):
    value = (node.get("config") or {}).get("critical")
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _normalize_result(result):
    """Bare value → ``{'out': value}``; dicts pass through as port maps (tramo
    ``normalizeResult``). ``None`` stays ``None`` (emits nothing downstream)."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    return {"out": result}


def _step_value(result):
    """tramo ``stepValue``: single-port ``{out}`` flattens; multi-port keeps the map."""
    if result is None:
        return None
    keys = list(result.keys())
    if keys == ["out"]:
        return result["out"]
    return result


def _summarize_output(normalized):
    """Compact, human-readable output string for the run record (step_results shape)."""
    if normalized is None:
        return None
    value = _step_value(normalized)
    if value is None:
        return None
    if isinstance(value, str):
        return value[:2000]
    try:
        import json
        return json.dumps(value, default=str)[:2000]
    except (ValueError, TypeError):
        return str(value)[:2000]


def _compute_backoff(retry, attempt):
    """Port of runner.ts ``computeBackoff`` — attempt is 1-based (1 = first retry)."""
    base = max(0, int(retry.get("delayMs") or 0))
    backoff = retry.get("backoff") or "fixed"
    delay = base
    if backoff == "linear":
        delay = base * attempt
    elif backoff == "exponential":
        delay = base * (2 ** (attempt - 1))
    max_delay = retry.get("maxDelayMs")
    if max_delay is not None:
        delay = min(delay, max(0, int(max_delay)))
    if retry.get("jitter"):
        delay = delay * (0.5 + random.random())
    return max(0, int(round(delay)))
