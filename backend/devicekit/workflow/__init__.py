"""Graph automation engine (plan 22) — Python execution of tramo WorkflowDocs.

tramo (our npm package) owns the JSON contract (`WorkflowDoc`) and the visual editor;
this package owns runtime execution. tramo's TS runtime (`packages/runtime/src/runner.ts`)
is the reference semantics — the modules here port the subset DeviceKit uses:

- ``doc``      — document queries, Kahn validation (mirror of ``@tramo/spec`` ``topoSort``),
                 slug derivation, and the linear→graph compat shim.
- ``expr``     — AST-allowlist expression evaluator (replaces the JS ``new Function`` /
                 ServerKit sandboxed-``eval`` approach; safe for operator-authored docs).
- ``template`` — ``{{path.to.field}}`` interpolation (port of runtime ``template.ts``).
- ``rules``    — rule-tree evaluation for ``if``/``switch`` (port of spec ``rules.ts``).
- ``engine``   — the topological walk executor (runAfter gating, port routing, retry).

Divergence policy: when Python and tramo disagree, fix tramo at source or this port —
never fork semantics (see plan 22 "Decisions").
"""
from devicekit.workflow.doc import (
    topo_sort,
    validate_doc,
    linear_steps_to_doc,
    build_step_slug_map,
    slugify,
    is_workflow_doc,
)
from devicekit.workflow.engine import WorkflowEngine

__all__ = [
    "topo_sort",
    "validate_doc",
    "linear_steps_to_doc",
    "build_step_slug_map",
    "slugify",
    "is_workflow_doc",
    "WorkflowEngine",
]
