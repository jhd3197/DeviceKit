"""Control-flow node executors (plan 22 phase 2) — tramo builtins the Python engine
supports: ``if``, ``switch``, ``merge``, bounded ``for-each``, ``call-flow`` (+
``flow-output``, ``set-var``). Registered onto the executor table at import.

Semantics track ``@tramo/runtime`` ``executors.ts`` with two deliberate deviations:

- Expressions run through the AST-allowlist evaluator, never ``new Function``/``eval``.
  ``for-each`` bodies are therefore *expressions* over ``item``/``index``/``input``/
  ``vars``/``steps`` (a leading ``return …;`` from the editor default is tolerated and
  stripped) — free-form code bodies are out of scope by design.
- ``for-each`` is **bounded**: iteration stops at ``maxItems`` (default 1000) so an
  operator-authored doc can't spin unbounded on the host.
"""
import logging

from devicekit.workflow.executors import register_builtin
from devicekit.workflow.expr import safe_eval
from devicekit.workflow.rules import evaluate_rule_group, is_rule_group
from devicekit.workflow.template import parse_maybe_json, render_template

logger = logging.getLogger(__name__)

#: Default + hard ceiling for for-each iteration counts (bounded by design).
FOR_EACH_DEFAULT_MAX = 1000
FOR_EACH_HARD_MAX = 10000


# ---------------------------------------------------------------------------
# if / switch / merge
# ---------------------------------------------------------------------------

def _exec_if(engine, node, inputs):
    config = node.get("config") or {}
    env = engine.expr_env(inputs, node)
    rules = config.get("rules")
    if is_rule_group(rules) and rules.get("rules"):
        passed = evaluate_rule_group(rules, env)
    else:
        expression = str(config.get("condition") or "input")
        passed = bool(safe_eval(expression, env))
    return {"yes": inputs.get("in")} if passed else {"no": inputs.get("in")}


def _exec_switch(engine, node, inputs):
    config = node.get("config") or {}
    env = engine.expr_env(inputs, node)
    cases = config.get("cases")
    for case in cases if isinstance(cases, list) else []:
        key = str((case or {}).get("key") or "").strip()
        if not key or key == "default":
            continue
        rules = case.get("rules")
        if is_rule_group(rules) and rules.get("rules"):
            if evaluate_rule_group(rules, env):
                return {key: inputs.get("in")}
        else:
            # Empty rules in a case match anything — same convention as If.
            return {key: inputs.get("in")}
    return {"default": inputs.get("in")}


def _exec_merge(engine, node, inputs):
    mode = str((node.get("config") or {}).get("mode") or "object")
    values = [v for v in inputs.values() if v is not None]
    if mode == "array":
        return {"out": values}
    if mode == "first":
        return {"out": next((v for v in values if v is not None), None)}
    out = {}
    for v in values:
        if isinstance(v, dict):
            out.update(v)
    return {"out": out}


# ---------------------------------------------------------------------------
# for-each (bounded)
# ---------------------------------------------------------------------------

def _normalize_body(body):
    """Tolerate the editor's JS-flavored default (``return item;``) — the engine
    evaluates expressions, so strip the ``return``/``;`` wrapper when present."""
    src = (body or "").strip()
    if src.startswith("return "):
        src = src[len("return "):]
    return src.rstrip(";").strip() or "item"


def _exec_for_each(engine, node, inputs):
    config = node.get("config") or {}
    env = engine.expr_env(inputs, node)
    source_expr = str(config.get("source") or "input").strip() or "input"
    try:
        items = safe_eval(source_expr, env, strict=True)
    except ValueError as e:
        return {"error": {"message": f"for-each: source expression failed: {e}"}}
    if not isinstance(items, (list, tuple)):
        return {"error": {"message": f"for-each: source did not resolve to an array "
                                     f"(got {type(items).__name__})."}}

    max_items = min(int(config.get("maxItems") or FOR_EACH_DEFAULT_MAX), FOR_EACH_HARD_MAX)
    if len(items) > max_items:
        return {"error": {"message": f"for-each: source has {len(items)} items, over the "
                                     f"bound of {max_items} (raise maxItems if intended)."}}

    mode = str(config.get("mode") or "map")
    body = _normalize_body(str(config.get("body") or "item"))
    var_name = str(config.get("varName") or "").strip()
    if mode == "reduce-into-var":
        if not var_name:
            return {"error": {"message": "for-each: reduce-into-var requires a Target variable."}}
        if not isinstance(engine.vars.get(var_name), list):
            engine.vars[var_name] = []

    collected = []
    for index, item in enumerate(items):
        if engine.cancel_event.is_set():
            break
        value = safe_eval(body, engine.expr_env(inputs, node,
                                                extra={"item": item, "index": index}))
        if mode == "filter":
            if value:
                collected.append(item)
        elif mode == "reduce-into-var":
            engine.vars[var_name].append(value)
        else:
            collected.append(value)

    if mode == "reduce-into-var":
        return {"out": engine.vars[var_name]}
    return {"out": collected}


# ---------------------------------------------------------------------------
# call-flow — run another automation as a node (cycle-guarded)
# ---------------------------------------------------------------------------

def _exec_call_flow(engine, node, inputs):
    from devicekit.workflow.doc import is_workflow_doc, linear_steps_to_doc
    from devicekit.workflow.engine import WorkflowEngine, MAX_CALL_DEPTH

    config = node.get("config") or {}
    flow_id = str(config.get("flowId") or "").strip()
    if not flow_id:
        return {"error": {"message": "call-flow: no automation selected"}}
    client = engine.client
    if client is None or not hasattr(client, "get_automation"):
        return {"error": {"message": "call-flow: no automation store on this engine"}}
    if flow_id in engine.call_stack:
        return {"error": {"message": f"call-flow: cycle detected — automation "
                                     f"'{flow_id}' is already on the call stack"}}
    if engine.depth + 1 >= MAX_CALL_DEPTH:
        return {"error": {"message": f"call-flow: max sub-flow depth "
                                     f"({MAX_CALL_DEPTH}) exceeded"}}
    automation = client.get_automation(flow_id)
    if not automation:
        return {"error": {"message": f"call-flow: automation '{flow_id}' not found"}}
    sub_doc = automation.get("graph")
    if not is_workflow_doc(sub_doc):
        sub_doc = linear_steps_to_doc(automation)   # linear sub-automations run shimmed

    raw_inputs = config.get("inputs")
    if isinstance(raw_inputs, str):
        rendered = render_template(raw_inputs, inputs.get("in"), engine.vars,
                                   engine.steps, engine.trigger)
        parsed = parse_maybe_json(rendered)
        if isinstance(parsed, str):
            return {"error": {"message": "call-flow: inputs JSON invalid after rendering"}}
        parsed_inputs = parsed if parsed is not None else {}
    else:
        parsed_inputs = raw_inputs if raw_inputs is not None else {}

    device_id = config.get("device_id") or engine.device_id
    sub_engine = WorkflowEngine(
        client, sub_doc,
        device_id=device_id,
        trigger=parsed_inputs,
        cancel_event=engine.cancel_event,
        on_event=engine.on_event,
        run_id=f"{engine.run_id}:{flow_id}" if engine.run_id else flow_id,
        depth=engine.depth + 1,
        call_stack=engine.call_stack + [flow_id],
    )
    result = sub_engine.run()
    if result["status"] != "completed":
        return {"error": {"message": f"sub-flow '{automation.get('name', flow_id)}' "
                                     f"{result['status']}: {result['error'] or 'unknown error'}"}}

    # The sub-flow's return value is what its flow-output captured; with no
    # flow-output node, fall back to the last executed node's value.
    output_node = next((n for n in sub_doc.get("nodes", [])
                        if n.get("type") == "flow-output"), None)
    if output_node is not None:
        value = sub_engine.node_results.get(output_node["id"])
    else:
        value = None
        for n in reversed(sub_doc.get("nodes", [])):
            if n["id"] in sub_engine.node_results:
                value = sub_engine.node_results[n["id"]]
                break
    if isinstance(value, dict) and "out" in value:
        value = value["out"]
    return {"out": value}


def _exec_flow_output(engine, node, inputs):
    return {"in": inputs.get("in"), "out": inputs.get("in")}


# ---------------------------------------------------------------------------
# set-var — workflow-scoped variables ({{vars.NAME}})
# ---------------------------------------------------------------------------

def _exec_set_var(engine, node, inputs):
    config = node.get("config") or {}
    name = str(config.get("name") or "").strip()
    if not name:
        raise ValueError("set-var: variable name is required")
    rendered = render_template(str(config.get("value") or ""), inputs.get("in"),
                               engine.vars, engine.steps, engine.trigger)
    engine.vars[name] = parse_maybe_json(rendered)
    return {"out": inputs.get("in")}


register_builtin("if", _exec_if)
register_builtin("switch", _exec_switch)
register_builtin("merge", _exec_merge)
register_builtin("for-each", _exec_for_each)
register_builtin("call-flow", _exec_call_flow)
register_builtin("flow-output", _exec_flow_output)
register_builtin("set-var", _exec_set_var)
