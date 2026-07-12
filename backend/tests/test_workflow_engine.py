"""Plan 22 phase 1: the WorkflowDoc engine — Kahn validation, the topological walk,
port-based branch gating, `{{…}}` interpolation, the critical-abort contract, and the
linear→graph compat shim. Pure engine tests: `wait`/`adb`-free step types only, driven
synchronously with no job system.
"""
import pytest

from devicekit.mixins.automation import AutomationMixin
from devicekit.workflow import (
    WorkflowEngine, linear_steps_to_doc, topo_sort, validate_doc, slugify,
    build_step_slug_map,
)
from devicekit.workflow.executors import register_builtin, _BUILTINS
from devicekit.workflow.expr import safe_eval, UnsafeExpressionError, _translate_js
from devicekit.workflow.template import render_template


class _Client(AutomationMixin):
    """Bare step-registry host — enough client for dk.* nodes that need no device."""


def _doc(nodes, edges):
    return {"version": 1, "nodes": nodes, "edges": edges, "meta": {}}


def _wait_node(node_id, label=None, config=None, **extra):
    cfg = {"delay": 1}
    cfg.update(config or {})
    return {"id": node_id, "type": "dk.wait", "label": label or node_id,
            "config": cfg, **extra}


def _edge(source, target, source_handle=None):
    e = {"id": f"e_{source}_{target}", "source": source, "target": target}
    if source_handle:
        e["sourceHandle"] = source_handle
    return e


# ---------------------------------------------------------------------------
# Validation (mirror of @tramo/spec topoSort)
# ---------------------------------------------------------------------------

def test_topo_sort_orders_and_detects_cycles():
    doc = _doc(
        [{"id": "a", "type": "x", "config": {}},
         {"id": "b", "type": "x", "config": {}},
         {"id": "c", "type": "x", "config": {}}],
        [_edge("a", "b"), _edge("b", "c")])
    result = topo_sort(doc)
    assert result["ok"] and result["order"] == ["a", "b", "c"]

    doc["edges"].append(_edge("c", "a"))
    result = topo_sort(doc)
    assert not result["ok"]
    assert set(result["cycle"]) == {"a", "b", "c"}
    assert "Cycle detected" in result["error"]


def test_validate_doc_catches_structural_errors():
    assert not validate_doc({"version": 2, "nodes": [], "edges": [], "meta": {}})["ok"]
    bad_edge = validate_doc(_doc([{"id": "a", "type": "x", "config": {}}],
                                 [_edge("a", "ghost")]))
    assert any("unknown target" in e for e in bad_edge["errors"])
    dup = validate_doc(_doc([{"id": "a", "type": "x", "config": {}},
                             {"id": "a", "type": "y", "config": {}}], []))
    assert any("Duplicate node id" in e for e in dup["errors"])
    bad_after = validate_doc(_doc([{"id": "a", "type": "x", "config": {},
                                    "runAfter": "sometimes"}], []))
    assert any("runAfter" in e for e in bad_after["errors"])


# ---------------------------------------------------------------------------
# Slugs (mirror of @tramo/spec slug.ts)
# ---------------------------------------------------------------------------

def test_slugify_and_collision_suffixes():
    assert slugify("Fetch GitHub user {{user}}") == "fetch_github_user"
    doc = _doc([
        {"id": "n1", "type": "x", "label": "Do Thing", "config": {}},
        {"id": "n2", "type": "x", "label": "Do Thing", "config": {}},
    ], [])
    slug_to_id, id_to_slug = build_step_slug_map(doc)
    assert id_to_slug == {"n1": "do_thing", "n2": "do_thing_2"}
    assert slug_to_id["do_thing"] == "n1"


# ---------------------------------------------------------------------------
# Straight-line execution + compat shim
# ---------------------------------------------------------------------------

def test_straight_line_doc_runs_to_completion():
    doc = _doc(
        [{"id": "t", "type": "manual-trigger", "config": {}},
         _wait_node("w1"), _wait_node("w2")],
        [_edge("t", "w1"), _edge("w1", "w2")])
    engine = WorkflowEngine(_Client(), doc, device_id="serial-1")
    result = engine.run()
    assert result["ok"] and result["status"] == "completed"
    statuses = {r["node_id"]: r["status"] for r in result["records"]}
    assert statuses == {"t": "completed", "w1": "completed", "w2": "completed"}


def test_linear_shim_preserves_steps_and_runs():
    automation = {
        "name": "Legacy",
        "steps": [
            {"id": "s1", "type": "wait", "label": "w1", "config": {"delay": 1}},
            {"id": "s2", "type": "wait", "label": "w2", "config": {"delay": 1}},
        ],
    }
    doc = linear_steps_to_doc(automation)
    assert doc["meta"]["shim"] is True
    assert [n["type"] for n in doc["nodes"]] == ["manual-trigger", "dk.wait", "dk.wait"]
    # Shimmed steps keep abort-on-failure behavior.
    assert all(n["config"]["critical"] for n in doc["nodes"][1:])
    assert validate_doc(doc)["ok"]

    result = WorkflowEngine(_Client(), doc, device_id="serial-1").run()
    assert result["status"] == "completed"


def test_events_mirror_tramo_run_event_shapes():
    events = []
    doc = _doc([{"id": "t", "type": "manual-trigger", "config": {}}, _wait_node("w1")],
               [_edge("t", "w1")])
    WorkflowEngine(_Client(), doc, device_id="s", on_event=events.append,
                   run_id="r1").run()
    types = [e["type"] for e in events]
    assert types[0] == "run-start" and types[-1] == "run-end"
    assert "node-start" in types and "node-success" in types
    start = next(e for e in events if e["type"] == "run-start")
    assert start["nodeOrder"] == ["t", "w1"]
    success = next(e for e in events if e["type"] == "node-success")
    assert {"runId", "nodeId", "output", "durationMs"} <= set(success)


# ---------------------------------------------------------------------------
# Branch gating (port routing) — the core of the graph semantics
# ---------------------------------------------------------------------------

def test_unfired_port_skips_downstream_branch():
    register_builtin("test-branch", lambda eng, node, inputs: {"yes": "took-yes"})
    try:
        doc = _doc(
            [{"id": "t", "type": "manual-trigger", "config": {}},
             {"id": "gate", "type": "test-branch", "config": {}},
             _wait_node("on_yes"), _wait_node("on_no")],
            [_edge("t", "gate"),
             _edge("gate", "on_yes", source_handle="yes"),
             _edge("gate", "on_no", source_handle="no")])
        result = WorkflowEngine(_Client(), doc, device_id="s").run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["on_yes"] == "completed"
        assert statuses["on_no"] == "skipped"
        skipped = next(r for r in result["records"] if r["node_id"] == "on_no")
        assert 'did not emit port "no"' in skipped["output"]
        assert result["status"] == "completed"   # a gated-off branch is not a failure
    finally:
        _BUILTINS.pop("test-branch", None)


# ---------------------------------------------------------------------------
# Interpolation — {{steps.*}} / {{vars.*}} / {{trigger.*}} / legacy {{store_as}}
# ---------------------------------------------------------------------------

def test_render_template_roots():
    steps = {"fetch": {"login": "juan", "id": 7}}
    variables = {"otp": "123456"}
    trigger = {"body": {"device": "serial-9"}}
    assert render_template("{{steps.fetch.login}}", None, variables, steps) == "juan"
    assert render_template("{{vars.otp}}", None, variables, steps) == "123456"
    assert render_template("{{trigger.body.device}}", None, variables, steps,
                           trigger) == "serial-9"
    # Legacy flat store_as name falls back to the vars bag.
    assert render_template("{{otp}}", None, variables, steps) == "123456"
    # Missing paths render blank, never raise.
    assert render_template("{{steps.nope.x}}", None, variables, steps) == ""


def test_step_output_feeds_downstream_config():
    client = _Client()
    client.register_step_type("emit_struct", {
        "label": "Emit", "category": "Test", "config": {},
        "execute": lambda c, cfg, dev: {"results": [{"url": "https://x.test"}],
                                        "top": "first"},
    })
    seen = {}
    client.register_step_type("capture", {
        "label": "Capture", "category": "Test",
        "config": {"value": {"type": "text", "label": "v", "required": True}},
        "execute": lambda c, cfg, dev: seen.update(cfg) or "ok",
    })
    try:
        doc = _doc(
            [{"id": "t", "type": "manual-trigger", "config": {}},
             {"id": "emit", "type": "dk.emit_struct", "label": "serp",
              "config": {"store_as": "serp"}},
             {"id": "cap", "type": "dk.capture",
              "config": {"value": "{{steps.serp.top}} / {{serp_top_url}} / {{trigger.who}}"}}],
            [_edge("t", "emit"), _edge("emit", "cap")])
        result = WorkflowEngine(client, doc, device_id="s",
                                trigger={"who": "hook"}).run()
        assert result["status"] == "completed"
        assert seen["value"] == "first / https://x.test / hook"
    finally:
        client.unregister_step_type("emit_struct")
        client.unregister_step_type("capture")


# ---------------------------------------------------------------------------
# Failure contract: critical abort vs non-critical flow-through
# ---------------------------------------------------------------------------

def _register_failing(client):
    def _boom(c, cfg, dev):
        raise RuntimeError("boom")
    client.register_step_type("always_fails", {
        "label": "Fails", "category": "Test", "config": {}, "execute": _boom})


def test_critical_failure_aborts_run():
    client = _Client()
    _register_failing(client)
    try:
        doc = _doc(
            [{"id": "t", "type": "manual-trigger", "config": {}},
             {"id": "bad", "type": "dk.always_fails", "config": {"critical": True}},
             _wait_node("after")],
            [_edge("t", "bad"), _edge("bad", "after")])
        result = WorkflowEngine(client, doc, device_id="s").run()
        assert result["status"] == "failed"
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["bad"] == "failed"
        assert statuses["after"] == "skipped"
        assert "boom" in result["error"]
    finally:
        client.unregister_step_type("always_fails")


def test_noncritical_failure_without_error_branch_fails_run():
    client = _Client()
    _register_failing(client)
    try:
        doc = _doc(
            [{"id": "t", "type": "manual-trigger", "config": {}},
             {"id": "bad", "type": "dk.always_fails", "config": {}},
             _wait_node("after")],
            [_edge("t", "bad"), _edge("bad", "after")])
        result = WorkflowEngine(client, doc, device_id="s").run()
        # Downstream on-success skipped; the bare error fails the run.
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["after"] == "skipped"
        assert result["status"] == "failed"
        assert "without an error branch" in result["error"]
    finally:
        client.unregister_step_type("always_fails")


def test_on_error_branch_handles_failure():
    client = _Client()
    _register_failing(client)
    try:
        doc = _doc(
            [{"id": "t", "type": "manual-trigger", "config": {}},
             {"id": "bad", "type": "dk.always_fails", "config": {}},
             _wait_node("cleanup", runAfter="on-error")],
            [_edge("t", "bad"), _edge("bad", "cleanup")])
        result = WorkflowEngine(client, doc, device_id="s").run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["cleanup"] == "completed"
        # A compensation branch that ran counts as handling the error.
        assert result["status"] == "completed"
    finally:
        client.unregister_step_type("always_fails")


# ---------------------------------------------------------------------------
# Expression evaluator — AST allowlist, not eval
# ---------------------------------------------------------------------------

def test_safe_eval_js_subset():
    env = {"input": {"items": [1, 2, 3], "ok": True}, "vars": {"n": 5}}
    assert safe_eval("input.items", env) == [1, 2, 3]
    assert safe_eval("vars.n > 3 && input.ok", env) is True
    assert safe_eval("vars.n === 5 || false", env) is True
    assert safe_eval("!input.ok", env) is False
    assert safe_eval("input.missing", env) is None
    assert safe_eval("len(input.items)", env) == 3
    assert safe_eval("null", env) is None


def test_safe_eval_rejects_unsafe_syntax():
    env = {"vars": {}}
    # Lenient mode swallows the problem (a typo can't crash a run)…
    assert safe_eval("__import__('os').system('rm')", env) is None
    assert safe_eval("vars.__class__", env) is None
    assert safe_eval("open('x')", env) is None
    # …strict mode surfaces it.
    with pytest.raises(ValueError):
        safe_eval("__import__('os')", env, strict=True)


def test_js_translation_leaves_strings_alone():
    assert _translate_js("a && b") == "a  and  b"
    assert _translate_js("'a && b'") == "'a && b'"
    assert _translate_js("x !== null") == "x != None"
