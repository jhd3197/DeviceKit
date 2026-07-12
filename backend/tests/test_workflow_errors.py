"""Plan 22 phase 3: the error & retry contract — per-node RetryPolicy
({count, delayMs, backoff, maxDelayMs, jitter}), runAfter routing (on-error fallback
branches, always cleanup), error envelopes vs raises, and declarative compensation.
"""
from devicekit.mixins.automation import AutomationMixin
from devicekit.workflow import WorkflowEngine
from devicekit.workflow.engine import _compute_backoff


class _Client(AutomationMixin):
    pass


def _doc(nodes, edges):
    return {"version": 1, "nodes": nodes, "edges": edges, "meta": {}}


def _edge(source, target, source_handle=None, target_handle=None):
    e = {"id": f"e_{source}_{target}_{source_handle or 'out'}",
         "source": source, "target": target}
    if source_handle:
        e["sourceHandle"] = source_handle
    if target_handle:
        e["targetHandle"] = target_handle
    return e


def _trigger():
    return {"id": "t", "type": "manual-trigger", "config": {}}


def _wait(node_id, **extra):
    return {"id": node_id, "type": "dk.wait", "label": node_id,
            "config": {"delay": 1}, **extra}


def _flaky_client(fail_times, name="flaky"):
    """A client with a step type that raises `fail_times` times, then succeeds."""
    client = _Client()
    calls = {"n": 0}

    def _exec(c, cfg, dev):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise RuntimeError(f"transient #{calls['n']}")
        return f"ok after {calls['n']}"

    client.register_step_type(name, {
        "label": name, "category": "Test", "config": {}, "execute": _exec})
    return client, calls


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

def test_retry_recovers_transient_failures():
    client, calls = _flaky_client(fail_times=2)
    try:
        doc = _doc(
            [_trigger(),
             {"id": "f", "type": "dk.flaky", "config": {},
              "retry": {"count": 2, "delayMs": 0}}],
            [_edge("t", "f")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        assert result["status"] == "completed"
        rec = next(r for r in result["records"] if r["node_id"] == "f")
        assert rec["status"] == "completed"
        assert rec["attempts"] == 3
        assert calls["n"] == 3
    finally:
        client.unregister_step_type("flaky")


def test_retry_exhaustion_fails_node():
    client, calls = _flaky_client(fail_times=10)
    try:
        doc = _doc(
            [_trigger(),
             {"id": "f", "type": "dk.flaky", "config": {},
              "retry": {"count": 1, "delayMs": 0}}],
            [_edge("t", "f")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        assert result["status"] == "failed"
        rec = next(r for r in result["records"] if r["node_id"] == "f")
        assert rec["status"] == "failed" and rec["attempts"] == 2
        assert calls["n"] == 2
        assert "transient #2" in rec["error"]
    finally:
        client.unregister_step_type("flaky")


def test_no_retry_without_policy():
    client, calls = _flaky_client(fail_times=10)
    try:
        doc = _doc([_trigger(), {"id": "f", "type": "dk.flaky", "config": {}}],
                   [_edge("t", "f")])
        WorkflowEngine(client, doc, trigger={}).run()
        assert calls["n"] == 1
    finally:
        client.unregister_step_type("flaky")


def test_error_envelope_is_never_retried():
    """Returning {'error': …} is a routed outcome, not a failure (tramo contract)."""
    client = _Client()
    calls = {"n": 0}

    def _envelope(c, cfg, dev):
        calls["n"] += 1
        return None   # placeholder; replaced below via builtin

    from devicekit.workflow.executors import register_builtin, _BUILTINS

    def _emit_error(engine, node, inputs):
        calls["n"] += 1
        return {"error": {"message": "soft failure"}}

    register_builtin("test-error-envelope", _emit_error)
    try:
        doc = _doc(
            [_trigger(),
             {"id": "e", "type": "test-error-envelope", "config": {},
              "retry": {"count": 5, "delayMs": 0}},
             _wait("on_ok"), _wait("on_err")],
            [_edge("t", "e"),
             _edge("e", "on_ok", source_handle="out"),
             _edge("e", "on_err", source_handle="error")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        assert calls["n"] == 1                      # success — retry never engaged
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["e"] == "completed"
        assert statuses["on_err"] == "completed"    # error port fired…
        assert statuses["on_ok"] == "skipped"       # …out port did not
        assert result["status"] == "completed"
    finally:
        _BUILTINS.pop("test-error-envelope", None)


def test_compute_backoff_strategies():
    assert _compute_backoff({"count": 3, "delayMs": 100}, 1) == 100
    assert _compute_backoff({"count": 3, "delayMs": 100}, 3) == 100
    assert _compute_backoff({"count": 3, "delayMs": 100, "backoff": "linear"}, 3) == 300
    assert _compute_backoff({"count": 3, "delayMs": 100, "backoff": "exponential"}, 4) == 800
    assert _compute_backoff({"count": 3, "delayMs": 100, "backoff": "exponential",
                             "maxDelayMs": 250}, 4) == 250
    jittered = _compute_backoff({"count": 1, "delayMs": 100, "jitter": True}, 1)
    assert 50 <= jittered <= 150
    assert _compute_backoff({"count": 1}, 1) == 0


# ---------------------------------------------------------------------------
# runAfter routing
# ---------------------------------------------------------------------------

def _register_failing(client, name="always_fails"):
    def _boom(c, cfg, dev):
        raise RuntimeError("boom")
    client.register_step_type(name, {
        "label": name, "category": "Test", "config": {}, "execute": _boom})


def test_always_runs_on_both_outcomes():
    client = _Client()
    _register_failing(client)
    try:
        doc = _doc(
            [_trigger(),
             {"id": "bad", "type": "dk.always_fails", "config": {}},
             _wait("cleanup", runAfter="always")],
            [_edge("t", "bad"), _edge("bad", "cleanup")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["cleanup"] == "completed"
        # `always` counts as handling the upstream error (cleanup ran).
        assert result["status"] == "completed"

        doc_ok = _doc(
            [_trigger(), _wait("fine"), _wait("cleanup", runAfter="always")],
            [_edge("t", "fine"), _edge("fine", "cleanup")])
        result = WorkflowEngine(client, doc_ok, trigger={}).run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["cleanup"] == "completed"
    finally:
        client.unregister_step_type("always_fails")


def test_on_error_skips_when_all_upstreams_succeed():
    doc = _doc(
        [_trigger(), _wait("fine"), _wait("fallback", runAfter="on-error")],
        [_edge("t", "fine"), _edge("fine", "fallback")])
    result = WorkflowEngine(_Client(), doc, trigger={}).run()
    rec = next(r for r in result["records"] if r["node_id"] == "fallback")
    assert rec["status"] == "skipped"
    assert "no upstream errored" in rec["output"]
    assert result["status"] == "completed"


def test_compensation_branch_after_risky_node():
    """The declarative compensation story: an on-error branch hanging off the risky
    node runs the rollback, and the run reports completed (handled) — while the
    happy-path continuation is skipped."""
    client = _Client()
    _register_failing(client, "risky")
    try:
        doc = _doc(
            [_trigger(),
             {"id": "risky", "type": "dk.risky", "config": {}},
             _wait("continue_ok"),
             _wait("rollback", runAfter="on-error"),
             _wait("notify", runAfter="always")],
            [_edge("t", "risky"),
             _edge("risky", "continue_ok"),
             _edge("risky", "rollback"),
             _edge("rollback", "notify")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses == {"t": "completed", "risky": "failed",
                            "continue_ok": "skipped", "rollback": "completed",
                            "notify": "completed"}
        assert result["status"] == "completed"
    finally:
        client.unregister_step_type("risky")


def test_failed_compensation_fails_the_run():
    client = _Client()
    _register_failing(client, "risky")
    _register_failing(client, "bad_rollback")
    try:
        doc = _doc(
            [_trigger(),
             {"id": "risky", "type": "dk.risky", "config": {}},
             {"id": "rollback", "type": "dk.bad_rollback", "config": {},
              "runAfter": "on-error"}],
            [_edge("t", "risky"), _edge("risky", "rollback")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        assert result["status"] == "failed"
        assert "without an error branch" in result["error"]
    finally:
        client.unregister_step_type("risky")
        client.unregister_step_type("bad_rollback")


def test_critical_overrides_error_branches():
    """critical: true aborts immediately — even a wired on-error branch is skipped
    (the shim uses this to preserve linear abort-on-failure semantics)."""
    client = _Client()
    _register_failing(client, "risky")
    try:
        doc = _doc(
            [_trigger(),
             {"id": "risky", "type": "dk.risky", "config": {"critical": True}},
             _wait("rollback", runAfter="on-error")],
            [_edge("t", "risky"), _edge("risky", "rollback")])
        result = WorkflowEngine(client, doc, trigger={}).run()
        statuses = {r["node_id"]: r["status"] for r in result["records"]}
        assert statuses["rollback"] == "skipped"
        assert result["status"] == "failed"
    finally:
        client.unregister_step_type("risky")
