"""Parallel device fan-out (plan 22 phase 5) — the ``dk.device-fan-out`` node.

The one thing an inline engine can't do: a fan-out node dispatches **one durable job
per device branch** on the plan-05 queue (each branch is a full sub-automation run with
its own AutomationRun record), keeps at most ``concurrency`` branches in flight, bounds
each branch with a per-device timeout (a slow device never stalls the whole run), and
collects results back into the parent run.

Deliberate limits (this is a single-process dev tool, not a cluster):

- Device count is bounded (``MAX_FANOUT_DEVICES``).
- Effective concurrency is additionally capped at ``JOB_WORKERS - 1`` — the parent run
  occupies one worker while it waits, so branches always have a worker to land on.
  Several simultaneous fan-outs degrade to slower (timeout-bounded) progress, never a
  permanent deadlock.
"""
import logging
import time

from devicekit.workflow.expr import safe_eval
from devicekit.workflow.template import parse_maybe_json, render_template

logger = logging.getLogger(__name__)

MAX_FANOUT_DEVICES = 100
DEFAULT_CONCURRENCY = 3
DEFAULT_TIMEOUT_SECONDS = 600
POLL_INTERVAL = 0.25


def _resolve_devices(engine, node, inputs):
    """Device ids from the node config: an explicit ``devices`` value (expression,
    JSON list, or comma-separated serials) or an ``fql`` fleet query. Returns a list
    of ids, or raises ValueError with the reason."""
    config = node.get("config") or {}
    devices_raw = str(config.get("devices") or "").strip()
    fql = str(config.get("fql") or "").strip()

    if devices_raw:
        rendered = render_template(devices_raw, inputs.get("in"), engine.vars,
                                   engine.steps, engine.trigger)
        value = parse_maybe_json(rendered)
        if isinstance(value, str):
            # An expression counts only when it resolves to real values —
            # "d1, d2, d3" parses as a tuple of unknown names (all None), so it
            # falls through to the comma-split reading.
            evaluated = safe_eval(value, engine.expr_env(inputs, node))
            if (isinstance(evaluated, (list, tuple)) and evaluated
                    and all(e is not None for e in evaluated)):
                value = list(evaluated)
            else:
                value = [s.strip() for s in value.split(",") if s.strip()]
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("devices did not resolve to a non-empty list")
        ids = []
        for entry in value:
            if isinstance(entry, dict):
                entry = entry.get("device_id") or entry.get("serial")
            if entry:
                ids.append(str(entry))
        if not ids:
            raise ValueError("devices resolved to an empty list")
        return ids

    if fql:
        client = engine.client
        if not hasattr(client, "execute_fleet_query") or \
                not hasattr(client, "all_devices_for_query"):
            raise ValueError("FQL targeting needs the fleet-query mixin")
        matches = client.execute_fleet_query(fql, devices=client.all_devices_for_query())
        ids = [str(d.get("device_id") or d.get("serial"))
               for d in matches if d.get("device_id") or d.get("serial")]
        if not ids:
            raise ValueError(f"FQL matched no devices: {fql}")
        return ids

    raise ValueError("set either a devices list or an FQL query")


def _exec_device_fan_out(engine, node, inputs):
    config = node.get("config") or {}
    client = engine.client
    if client is None or not hasattr(client, "enqueue_run"):
        return {"error": {"message": "device-fan-out: no run funnel on this engine"}}

    automation_id = str(config.get("automation_id") or "").strip()
    if not automation_id:
        return {"error": {"message": "device-fan-out: no automation selected"}}
    if automation_id in engine.call_stack:
        return {"error": {"message": f"device-fan-out: cycle detected — automation "
                                     f"'{automation_id}' is already on the call stack"}}
    if not client.get_automation(automation_id):
        return {"error": {"message": f"device-fan-out: automation '{automation_id}' "
                                     f"not found"}}

    try:
        device_ids = _resolve_devices(engine, node, inputs)
    except ValueError as e:
        return {"error": {"message": f"device-fan-out: {e}"}}
    if len(device_ids) > MAX_FANOUT_DEVICES:
        return {"error": {"message": f"device-fan-out: {len(device_ids)} devices is over "
                                     f"the bound of {MAX_FANOUT_DEVICES}"}}

    raw_inputs = config.get("inputs")
    if isinstance(raw_inputs, str):
        rendered = render_template(raw_inputs, inputs.get("in"), engine.vars,
                                   engine.steps, engine.trigger)
        branch_inputs = parse_maybe_json(rendered)
        if not isinstance(branch_inputs, dict):
            branch_inputs = {}
    else:
        branch_inputs = raw_inputs if isinstance(raw_inputs, dict) else {}

    try:
        concurrency = max(1, int(config.get("concurrency") or DEFAULT_CONCURRENCY))
    except (TypeError, ValueError):
        concurrency = DEFAULT_CONCURRENCY
    try:
        from devicekit.mixins.jobs import JOB_WORKERS
        concurrency = min(concurrency, max(1, JOB_WORKERS - 1))
    except Exception:
        pass
    try:
        timeout_s = float(config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT_SECONDS

    results = {}
    pending = {}   # device_id -> (run_id, dispatched_at)
    queue = list(device_ids)
    cancelled = False

    def _dispatch(device_id):
        trigger = {"parent_run_id": engine.run_id, "device_id": device_id,
                   **branch_inputs}
        run = client.enqueue_run(automation_id, device_id=device_id,
                                 trigger_type="fanout", trigger=trigger)
        pending[device_id] = (run["id"], time.time())

    while queue or pending:
        if engine.cancel_event.is_set():
            cancelled = True
            break
        while queue and len(pending) < concurrency:
            device_id = queue.pop(0)
            try:
                _dispatch(device_id)
            except Exception as e:
                results[device_id] = {"status": "failed", "error": str(e),
                                      "run_id": None}
        for device_id in list(pending):
            run_id, started = pending[device_id]
            run = client.get_automation_run(run_id) or {}
            status = run.get("status")
            if status in ("completed", "failed", "cancelled"):
                results[device_id] = {
                    "status": status,
                    "run_id": run_id,
                    "completed_steps": run.get("completed_steps"),
                    "error": run.get("error"),
                }
                del pending[device_id]
            elif time.time() - started > timeout_s:
                try:
                    client.cancel_automation_run(run_id)
                except Exception:
                    pass
                results[device_id] = {"status": "timeout", "run_id": run_id,
                                      "error": f"no result within {timeout_s:.0f}s"}
                del pending[device_id]
        if pending:
            if engine.cancel_event.wait(POLL_INTERVAL):
                cancelled = True
                break

    if cancelled:
        for device_id, (run_id, _) in pending.items():
            try:
                client.cancel_automation_run(run_id)
            except Exception:
                pass
            results[device_id] = {"status": "cancelled", "run_id": run_id,
                                  "error": "parent run cancelled"}
        for device_id in queue:
            results[device_id] = {"status": "cancelled", "run_id": None,
                                  "error": "parent run cancelled"}

    succeeded = sum(1 for r in results.values() if r["status"] == "completed")
    failed = len(results) - succeeded
    summary = {"results": results, "devices": len(results),
               "succeeded": succeeded, "failed": failed}
    if failed:
        return {"error": {"message": f"{failed}/{len(results)} device branch(es) did "
                                     f"not complete", **summary}}
    return {"out": summary}


def register(register_builtin):
    register_builtin("dk.device-fan-out", _exec_device_fan_out)
