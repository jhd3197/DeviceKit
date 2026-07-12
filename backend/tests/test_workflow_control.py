"""Plan 22 phase 2: control-flow nodes (if / switch / merge / bounded for-each /
call-flow / set-var) and the DeviceKit node pack generated from the step-type
registry. Engine-level tests, no job system.
"""
import pytest

from devicekit.mixins.automation import AutomationMixin, STEP_TYPES
from devicekit.mixins.workflow import WorkflowMixin
from devicekit.workflow import WorkflowEngine, build_node_pack
from devicekit.workflow.node_pack import SUPPORTED_BUILTINS


class _Client(AutomationMixin, WorkflowMixin):
    """Step registry + automation store, enough for call-flow (no job system)."""


def _doc(nodes, edges):
    return {"version": 1, "nodes": nodes, "edges": edges, "meta": {}}


def _edge(source, target, source_handle=None):
    e = {"id": f"e_{source}_{target}", "source": source, "target": target}
    if source_handle:
        e["sourceHandle"] = source_handle
    return e


def _trigger(node_id="t"):
    return {"id": node_id, "type": "manual-trigger", "config": {}}


def _wait(node_id, **cfg):
    return {"id": node_id, "type": "dk.wait", "label": node_id,
            "config": {"delay": 1, **cfg}}


# ---------------------------------------------------------------------------
# if — rule tree first, AST expression fallback, yes/no ports
# ---------------------------------------------------------------------------

def test_if_routes_on_expression():
    doc = _doc(
        [_trigger(),
         {"id": "gate", "type": "if", "config": {"condition": "trigger.n > 3"}},
         _wait("yes_branch"), _wait("no_branch")],
        [_edge("t", "gate"),
         _edge("gate", "yes_branch", source_handle="yes"),
         _edge("gate", "no_branch", source_handle="no")])

    result = WorkflowEngine(_Client(), doc, trigger={"n": 5}).run()
    statuses = {r["node_id"]: r["status"] for r in result["records"]}
    assert statuses["yes_branch"] == "completed" and statuses["no_branch"] == "skipped"

    result = WorkflowEngine(_Client(), doc, trigger={"n": 1}).run()
    statuses = {r["node_id"]: r["status"] for r in result["records"]}
    assert statuses["no_branch"] == "completed" and statuses["yes_branch"] == "skipped"


def test_if_rule_tree_wins_over_expression():
    rules = {"kind": "group", "combinator": "and", "rules": [
        {"kind": "condition", "left": "input.level", "op": ">=", "right": 50},
        {"kind": "condition", "left": "input.name", "op": "starts-with", "right": "SM-"},
    ]}
    doc = _doc(
        [_trigger(),
         {"id": "gate", "type": "if",
          "config": {"rules": rules, "condition": "false"}},
         _wait("ok")],
        [_edge("t", "gate"), _edge("gate", "ok", source_handle="yes")])
    result = WorkflowEngine(_Client(), doc,
                            trigger={"level": 80, "name": "SM-S134DL"}).run()
    assert {r["node_id"]: r["status"] for r in result["records"]}["ok"] == "completed"


def test_empty_if_takes_yes_branch():
    doc = _doc(
        [_trigger(), {"id": "gate", "type": "if", "config": {}}, _wait("ok")],
        [_edge("t", "gate"), _edge("gate", "ok", source_handle="yes")])
    result = WorkflowEngine(_Client(), doc, trigger={"anything": 1}).run()
    assert result["status"] == "completed"
    assert {r["node_id"]: r["status"] for r in result["records"]}["ok"] == "completed"


# ---------------------------------------------------------------------------
# switch — first matching case wins, default port otherwise
# ---------------------------------------------------------------------------

def test_switch_routes_first_match_then_default():
    cases = [
        {"key": "android13", "label": "A13", "rules": {
            "kind": "group", "combinator": "and", "rules": [
                {"kind": "condition", "left": "input.api", "op": "=", "right": 33}]}},
        {"key": "android12", "label": "A12", "rules": {
            "kind": "group", "combinator": "and", "rules": [
                {"kind": "condition", "left": "input.api", "op": "=", "right": 31}]}},
    ]
    nodes = [_trigger(),
             {"id": "sw", "type": "switch", "config": {"cases": cases}},
             _wait("a13"), _wait("a12"), _wait("other")]
    edges = [_edge("t", "sw"),
             _edge("sw", "a13", source_handle="android13"),
             _edge("sw", "a12", source_handle="android12"),
             _edge("sw", "other", source_handle="default")]

    result = WorkflowEngine(_Client(), _doc(nodes, edges), trigger={"api": 31}).run()
    statuses = {r["node_id"]: r["status"] for r in result["records"]}
    assert statuses["a12"] == "completed"
    assert statuses["a13"] == "skipped" and statuses["other"] == "skipped"

    result = WorkflowEngine(_Client(), _doc(nodes, edges), trigger={"api": 28}).run()
    statuses = {r["node_id"]: r["status"] for r in result["records"]}
    assert statuses["other"] == "completed"


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def test_merge_modes():
    client = _Client()
    client.register_step_type("emit_a", {
        "label": "A", "category": "Test", "config": {},
        "execute": lambda c, cfg, dev: {"a": 1}})
    client.register_step_type("emit_b", {
        "label": "B", "category": "Test", "config": {},
        "execute": lambda c, cfg, dev: {"b": 2}})
    try:
        doc = _doc(
            [_trigger(),
             {"id": "na", "type": "dk.emit_a", "config": {}},
             {"id": "nb", "type": "dk.emit_b", "config": {}},
             {"id": "m", "type": "merge", "config": {"mode": "object"}}],
            [_edge("t", "na"), _edge("t", "nb"),
             {"id": "ea", "source": "na", "target": "m", "targetHandle": "a"},
             {"id": "eb", "source": "nb", "target": "m", "targetHandle": "b"}])
        engine = WorkflowEngine(client, doc, trigger={})
        result = engine.run()
        assert result["status"] == "completed"
        assert engine.node_results["m"]["out"] == {"a": 1, "b": 2}
    finally:
        client.unregister_step_type("emit_a")
        client.unregister_step_type("emit_b")


# ---------------------------------------------------------------------------
# for-each — bounded, AST body, map/filter/reduce modes
# ---------------------------------------------------------------------------

def _run_for_each(config, trigger):
    doc = _doc(
        [_trigger(), {"id": "fe", "type": "for-each", "config": config}],
        [_edge("t", "fe")])
    engine = WorkflowEngine(_Client(), doc, trigger=trigger)
    result = engine.run()
    return engine, result


def test_for_each_map_and_filter():
    engine, result = _run_for_each(
        {"source": "input.items", "mode": "map", "body": "item.n * 2"},
        {"items": [{"n": 1}, {"n": 2}, {"n": 3}]})
    assert result["status"] == "completed"
    assert engine.node_results["fe"]["out"] == [2, 4, 6]

    engine, _ = _run_for_each(
        {"source": "input.items", "mode": "filter", "body": "item.n > 1"},
        {"items": [{"n": 1}, {"n": 2}, {"n": 3}]})
    assert engine.node_results["fe"]["out"] == [{"n": 2}, {"n": 3}]


def test_for_each_tolerates_editor_return_body():
    engine, _ = _run_for_each(
        {"source": "input.items", "body": "return item.name;"},
        {"items": [{"name": "a"}, {"name": "b"}]})
    assert engine.node_results["fe"]["out"] == ["a", "b"]


def test_for_each_is_bounded():
    engine, result = _run_for_each(
        {"source": "input.items", "maxItems": 2},
        {"items": [1, 2, 3]})
    # Over-bound source routes out the error port; nothing runs unbounded.
    assert "over the bound" in engine.node_results["fe"]["error"]["message"]
    assert result["status"] == "completed"   # error envelope, not a raise


def test_for_each_non_array_source_errors():
    engine, _ = _run_for_each({"source": "input.nope"}, {"items": []})
    assert "did not resolve to an array" in engine.node_results["fe"]["error"]["message"]


# ---------------------------------------------------------------------------
# call-flow — sub-automations, linear shim fallback, cycle guard
# ---------------------------------------------------------------------------

def test_call_flow_runs_sub_automation_and_returns_flow_output(fresh_db):
    client = _Client()
    client.register_step_type("shout", {
        "label": "Shout", "category": "Test",
        "config": {"word": {"type": "text", "label": "w", "required": True}},
        "execute": lambda c, cfg, dev: str(cfg["word"]).upper()})
    try:
        sub = client.create_automation("Sub", graph=_doc(
            [{"id": "fi", "type": "flow-input", "config": {}},
             {"id": "s", "type": "dk.shout", "label": "shout",
              "config": {"word": "{{steps.flow_input.word}}"}},
             {"id": "fo", "type": "flow-output", "config": {}}],
            [_edge("fi", "s"), _edge("s", "fo")]))

        parent_doc = _doc(
            [_trigger(),
             {"id": "call", "type": "call-flow",
              "config": {"flowId": sub["id"], "inputs": '{"word": "hello"}'}}],
            [_edge("t", "call")])
        engine = WorkflowEngine(client, parent_doc, trigger={})
        result = engine.run()
        assert result["status"] == "completed"
        assert engine.node_results["call"]["out"] == "HELLO"
    finally:
        client.unregister_step_type("shout")


def test_call_flow_runs_linear_automation_via_shim(fresh_db):
    client = _Client()
    sub = client.create_automation("Legacy sub", steps=[
        {"id": "s1", "type": "wait", "label": "w", "config": {"delay": 1}},
    ])
    parent_doc = _doc(
        [_trigger(),
         {"id": "call", "type": "call-flow", "config": {"flowId": sub["id"]}}],
        [_edge("t", "call")])
    engine = WorkflowEngine(client, parent_doc, trigger={}, device_id="serial-1")
    result = engine.run()
    assert result["status"] == "completed"
    assert "error" not in (engine.node_results["call"] or {})


def test_call_flow_cycle_guard(fresh_db):
    client = _Client()
    a = client.create_automation("Self caller", graph={"version": 1, "nodes": [],
                                                       "edges": [], "meta": {}})
    # Wire the automation to call itself.
    doc = _doc(
        [_trigger(),
         {"id": "call", "type": "call-flow", "config": {"flowId": a["id"]}}],
        [_edge("t", "call")])
    client.save_automation_graph(a["id"], doc)

    engine = WorkflowEngine(client, doc, trigger={}, call_stack=[a["id"]])
    result = engine.run()
    assert "cycle detected" in engine.node_results["call"]["error"]["message"]
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# set-var + typed vars
# ---------------------------------------------------------------------------

def test_set_var_parses_json_and_feeds_templates():
    client = _Client()
    seen = {}
    client.register_step_type("capture", {
        "label": "Capture", "category": "Test",
        "config": {"value": {"type": "text", "label": "v", "required": True}},
        "execute": lambda c, cfg, dev: seen.update(cfg) or "ok"})
    try:
        doc = _doc(
            [_trigger(),
             {"id": "sv", "type": "set-var",
              "config": {"name": "limits", "value": '{"max": 4}'}},
             {"id": "cap", "type": "dk.capture",
              "config": {"value": "{{vars.limits.max}}"}}],
            [_edge("t", "sv"), _edge("sv", "cap")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        assert result["status"] == "completed"
        assert seen["value"] == "4"
    finally:
        client.unregister_step_type("capture")


# ---------------------------------------------------------------------------
# Node pack
# ---------------------------------------------------------------------------

def test_node_pack_maps_step_registry_to_tramo_defs():
    client = _Client()
    pack = client.get_node_pack()
    assert pack["integration"]["id"] == "devicekit"
    # Every step type + the pack's own event trigger (plan 22 part 4).
    assert pack["count"] == len(STEP_TYPES) + 1
    by_id = {n["id"]: n for n in pack["nodes"]}

    tap = by_id["dk.tap"]
    assert tap["integrationId"] == "devicekit"
    assert tap["inputs"] == [{"key": "in", "label": "In", "type": "any"}]
    field_keys = [f["key"] for f in tap["fields"]]
    assert field_keys[:2] == ["x", "y"]
    assert {"device_id", "critical", "store_as"} <= set(field_keys)

    swipe = by_id["dk.swipe"]
    direction = next(f for f in swipe["fields"] if f["key"] == "direction")
    assert direction["type"] == "select"
    assert {"label": "up", "value": "up"} in direction["options"]
    assert direction["optional"] is False

    assert "if" in pack["supported_builtins"]
    assert "js-transform" not in pack["supported_builtins"]


def test_node_pack_includes_extension_step_types():
    client = _Client()
    client.register_step_type("ext_step", {
        "label": "Ext", "category": "Custom", "config": {},
        "execute": lambda c, cfg, dev: "x"})
    try:
        pack = client.get_node_pack()
        assert any(n["id"] == "dk.ext_step" for n in pack["nodes"])
    finally:
        client.unregister_step_type("ext_step")


def test_supported_builtins_all_resolve():
    from devicekit.workflow.executors import _BUILTINS
    for type_name in SUPPORTED_BUILTINS:
        assert type_name in _BUILTINS, type_name
