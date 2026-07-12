"""Node executors for the Python workflow engine.

An executor is ``fn(engine, node, inputs) -> port-map | bare value | None``. Raising
marks the node errored (and triggers its retry policy); returning ``{'error': …}`` is a
normal success routed out the ``error`` port (tramo contract).

Two families:

- **tramo builtins** DeviceKit supports (triggers now; logic nodes land in plan 22
  phase 2). ``js-transform`` is deliberately absent — no free-form code execution on
  the host (plan 22 out-of-scope).
- **``dk.<step_type>`` nodes** — every entry of the plan-15 step-type registry
  (core + extension-contributed) executes through the same dispatch the linear engine
  uses, with config interpolated against ``{{steps.*}}``/``{{vars.*}}``/``{{trigger.*}}``
  first.
"""
import logging

from devicekit.workflow.doc import DK_STEP_PREFIX
from devicekit.workflow.template import render_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Triggers — pass-throughs; the real trigger payload arrives via engine.trigger
# (webhook body, cron tick, event data), same as tramo's HTTP layer populating
# options.trigger before run().
# ---------------------------------------------------------------------------

def _exec_manual_trigger(engine, node, inputs):
    from devicekit.workflow.template import parse_maybe_json
    payload = inputs.get("in")
    if payload in (None, {}, ""):
        payload = parse_maybe_json((node.get("config") or {}).get("payload")) or {}
    return {"out": payload}


def _exec_webhook_trigger(engine, node, inputs):
    payload = inputs.get("in")
    if payload in (None, ""):
        payload = {"body": None, "headers": {}, "query": {}}
    return {"out": payload}


def _exec_cron_trigger(engine, node, inputs):
    import time
    payload = inputs.get("in")
    if isinstance(payload, dict) and payload:
        return {"out": payload}
    return {"out": {"firedAt": time.time()}}


_BUILTINS = {
    "manual-trigger": _exec_manual_trigger,
    "webhook-trigger": _exec_webhook_trigger,
    "cron-trigger": _exec_cron_trigger,
    "flow-input": _exec_manual_trigger,   # caller input, else config sample payload
}


def register_builtin(type_name, fn):
    """Extend the builtin executor table (used by control-flow modules)."""
    _BUILTINS[type_name] = fn


# ---------------------------------------------------------------------------
# DeviceKit step nodes — dk.<step_type>
# ---------------------------------------------------------------------------

def _make_step_executor(step_type):
    def _exec_step(engine, node, inputs):
        client = engine.client
        if client is None or not hasattr(client, "step_type_registry"):
            raise ValueError("No step-type registry available on this engine")
        spec = client.step_type_registry().get(step_type)
        if spec is None:
            raise ValueError(f"Unknown step type: {step_type}")
        executor = spec.get("execute")
        if not callable(executor):
            raise ValueError(f"Step type '{step_type}' has no executor")

        raw_config = dict(node.get("config") or {})
        raw_config.pop("critical", None)   # engine-level flag, not a step param
        config = render_config(
            raw_config,
            context=inputs.get("in"),
            variables=engine.vars,
            steps=engine.steps,
            trigger=engine.trigger,
        )
        device_id = config.pop("device_id", None) or engine.device_id
        output = executor(client, config, device_id)

        # Legacy `store_as` capture keeps pre-graph `{{name}}` refs working, and the
        # flattened `{name}_{key}` derivations (plan 17) with them.
        if raw_config.get("store_as"):
            from devicekit.mixins.automation import AutomationMixin
            AutomationMixin._store_step_var(
                engine.vars, {"config": {"store_as": raw_config["store_as"]}}, output)
        return {"out": output}

    return _exec_step


def resolve_executor(engine, node):
    """Executor lookup for a node type: builtins first, then ``dk.*`` step dispatch."""
    node_type = node.get("type") or ""
    builtin = _BUILTINS.get(node_type)
    if builtin is not None:
        return builtin
    if node_type.startswith(DK_STEP_PREFIX):
        return _make_step_executor(node_type[len(DK_STEP_PREFIX):])
    return None
