# Plan 22 — Automation Engine v2: DAG + Triggers (tramo-powered)

**Status:** ✅ shipped — all six phases (stretch NL-patch bridge not started)
**Inspired by:** plan 18 calls the current engine "the linear automation engine" — an ordered list
of steps with no branching, loops, parallelism, or sub-flows. Two sources shape the upgrade:

1. **ServerKit's** `backend/app/services/workflow_engine.py` — the *executor* reference. Workflows
   are a nodes+edges graph executed by a **Kahn topological walk**, with a branch-gate
   (`_is_node_reachable` only runs nodes fed by an *active* branch), a per-node
   `{success, critical}` contract, per-node retry, and template interpolation. Its
   `backend/app/api/workflows.py` funnels **four trigger types — manual / webhook / cron /
   event —** through one `enqueue_execution`, including a public `POST /hooks/<webhook_id>` where
   the id *is* the token, plus an event bus turning internal events into runs (per-workflow
   cooldown).
2. **tramo** (`C:\Users\Juan\Documents\GitHub\tramo`, npm `tramo@0.1.x`, ours) — the *document
   model and editor*. tramo's `WorkflowDoc` is the same nodes+edges design plan 22 was going to
   invent, already specified, versioned, and shipped with a full visual editor (custom canvas, no
   XYFlow dep), a step picker, per-node config rail, `{{steps.<slug>.<path>}}` variable chips,
   undo/redo, version diff, and live run visualization. We adopt `WorkflowDoc` as the stored
   format and embed the tramo editor instead of building a canvas.

**The split:** tramo owns the JSON contract and the UI; DeviceKit's Python backend owns
execution. tramo's TypeScript runtime is **not** used at runtime — it serves as the reference
semantics for the Python executor. One doc, two implementations, backend is authoritative.

**Depends on:** 05/25 (jobs/queue — each run executes as a cancellable, restart-safe job; the
substrate for real parallel fan-out), 15 (step-type registry — the node executors), 06
(notification bus — the event-trigger source), **tramo** (npm: `tramo` umbrella package — editor
components + spec; owned, gaps fixed at source per the Prompture/Tukuy policy). Soft: 30
(frontend foundations — a route to mount the editor in), 20 (scoped webhook tokens).

## Why tramo fits (verified against both sources)

| Plan 22 needs | tramo already specifies |
|---|---|
| nodes+edges JSON on the Automation row | `WorkflowDoc` — `{version, nodes, edges, meta}`; `@tramo/spec` is zero-dep |
| edges carry a `sourceHandle` for branching | `WorkflowEdge.sourceHandle` / `targetHandle` (default ports `out`/`in`) |
| `logic_if` / bounded loop / sub-automation nodes | built-in `if`, `switch`, `merge`, `for-each`, `loop-start`/`loop-end`, `call-flow` + `flow-input`/`flow-output` |
| per-node retry/backoff | `WorkflowNode.retry` — `{count, delayMs, backoff}` |
| `on_failure: abort \| continue` edges | `runAfter: 'on-success' \| 'on-error' \| 'always'` per node |
| interpolation | `{{steps.<slug>.<path>}}` refs with automatic rewrite on step rename |
| manual/webhook/cron triggers | `manual-trigger`, `webhook-trigger`, `cron-trigger` node types |
| cycle rejection at validate time | `topoSort()` (Kahn) exported from `@tramo/spec` — same check client- and server-side |
| Phase-6 canvas, palette, validate, dry-run | the entire `tramo/react` editor surface |

Bonus alignment: DeviceKit `STEP_TYPES` params (`{type: text|number|select, label, required,
default, options}` in `mixins/automation.py`) map nearly 1:1 onto tramo `NodeDefinition.fields`,
and tramo already synthesizes node definitions from external catalogs (`mcpServerToNodeDefs`) —
the exact pattern for turning the plan-15 registry (including extension-contributed step types)
into a DeviceKit node pack. tramo's node-level `sensitive`/`requiredRole` flags line up with
DeviceKit's gated-action model (plan 21). And tramo's README lists "a future Python runtime" —
this executor is effectively its first incarnation.

## Honest limitations to copy *around* (from reading ServerKit's source)

ServerKit's engine is a great executor model, but three of its properties are *not* what a device
fleet wants — port the shape, fix these:

1. **It executes sequentially** even though the graph models fan-out (`while ready: popleft`,
   single thread). For true parallel *device* fan-out, run per-device branches as **separate
   jobs** (plan 05) — don't inline them.
2. **It's acyclic** — cycles are rejected at validate time. Loops (retry-N, for-each-device) need
   an explicit **bounded-iteration node**, not graph cycles. (tramo agrees: its loops are
   `for-each` / `loop-start`+`loop-end` bracket nodes, planned over an acyclic doc.)
3. **Conditions use a sandboxed `eval()`** (`__builtins__={}` + a whitelist). For fleet operators
   who author automations, use a small **AST-allowlist expression evaluator** instead.

## The questions this plan answers

- **"Can a flow branch on a result?"** Yes — an `if` node routes on its `true`/`false` output
  ports; edges carry a `sourceHandle`; only nodes fed by the active branch run.
- **"Can it run across 50 devices at once, or retry, or call another automation?"** Yes — bounded
  `for-each` over a device list / FQL result, per-device branches dispatched as concurrency-capped
  jobs, per-node retry/backoff, and a `call-flow` node.
- **"Can something *outside* DeviceKit start an automation?"** Yes — a per-automation webhook URL
  (the id is the token), plus internal device events (offline, low battery, geofence) driving the
  same run path. All four trigger types funnel through one `enqueue_run`.
- **"Do we build a graph UI?"** No — we embed the one we already own.

## Part 1 — WorkflowDoc storage + Python executor (with a compat shim)

- Store a tramo `WorkflowDoc` (`{version, nodes, edges, meta}`) on the `Automation` row —
  adopt the spec verbatim rather than inventing a near-identical shape. `meta.revision` gives
  save-versioning for free.
- Validate with Kahn in-degree tracking (reject cycles with a clear "cycle detected at node X"),
  mirroring `@tramo/spec`'s `topoSort` so the editor and the backend agree on validity. Execute as
  a topological walk in Python.
- **Compatibility shim:** an existing linear automation becomes a straight-line `WorkflowDoc`
  automatically (`manual-trigger` → step → step …) — no user migration, the old step list still
  runs.
- Per-node contract: `{success, critical}` as in ServerKit; `critical` aborts, non-critical logs +
  continues. Interpolation uses tramo's syntax — `{{steps.<slug>.<path>}}`, `{{trigger.<path>}}`,
  `{{vars.<name>}}` — resolved by the AST-allowlist evaluator (not `eval`).

## Part 2 — Control-flow nodes + the DeviceKit node pack

- Adopt tramo's built-in node type names so the editor renders them natively:
  - `if` — 2-way branch-gate (tramo also ships `switch` and `merge`; implement `if` + `merge`
    first, `switch` when needed).
  - `for-each` — **bounded** iteration over a device list or FQL result; each iteration is a
    branch.
  - `call-flow` — call another automation as a node (cycle-guarded across automations).
- **DeviceKit node pack:** generate tramo `NodeDefinition`s from the plan-15 step-type registry
  (device steps like `tap`, `type_text`, `adb_shell`, `visual_check`, plus extension-contributed
  types) and serve them from an endpoint; the frontend folds them into the editor registry the
  same way tramo folds in MCP servers (`mcpServerToNodeDefs`). Field mapping is mechanical —
  both sides use `{type, label, required, default, options}`.
- Typed step variables so a downstream node can consume `{{steps.serp.top_url}}` etc. (the
  plan-17 `_store_step_var` flattening already prototypes this; tramo's variable chips are the UI
  for it).

## Part 3 — Error & retry contract (tramo vocabulary)

- Per-node retry via tramo's `RetryPolicy` — `{count, delayMs, backoff}` — executed by the Python
  engine.
- Failure routing via `runAfter`: a node marked `on-error` runs only when a predecessor failed
  (fallback/cleanup branches); `always` runs regardless. This replaces the bespoke
  `on_failure: abort | continue` edge — same power, already in the spec and the editor.
- **Compensation** is an `on-error` branch hanging off the risky node — first-class in the doc,
  no ad-hoc rollback (ServerKit only has ad-hoc rollback; this makes it declarative).

## Part 4 — Triggers (one `enqueue_run` for all four)

- Trigger nodes in the doc use tramo's types: **`manual-trigger`** (today) + **`webhook-trigger`**
  (`POST /hooks/<token>`, token *is* auth, wraps the POST body as `{{trigger.*}}`) +
  **`cron-trigger`** (plan 05 `ScheduledJob`) + a DeviceKit-pack **`event-trigger`** (plan 06 bus →
  `automation.dispatch` job → match active event-triggered automations by event type,
  per-automation cooldown to prevent storms).
- The webhook trigger is DeviceKit's answer to "external events can't start automations" — it and
  the event trigger are the reason this plan absorbs the inbound-webhook idea rather than a
  separate plan.

## Part 5 — Parallel device fan-out via jobs

- The one thing an inline engine *can't* do. A `for-each`-over-devices node dispatches one
  **job per device branch** on the queue (plan 05), concurrency-capped, results collected back
  into the parent run. This is where "run this automation across the whole fleet" becomes real and
  bounded (echoes plan 24's `fleet_sweep` discipline: bounded pool, per-device timeout, one slow
  device never stalls the run).

## Part 6 — Frontend: embed the tramo editor

- Replace the linear `AutomationEditor.jsx` surface with tramo's editor for graph automations:
  `useWorkflow` + `Canvas` + `RightRail` from `tramo/react` (+ `tramo/styles.css`), registry =
  tramo builtins ∪ the DeviceKit node pack from Part 2. React 18 + Vite already match tramo's
  peer deps; tramo ships compiled JS so the JSX (non-TS) frontend consumes it directly.
- Validation/dry-run: `topoSort` from `tramo/spec` client-side for instant cycle + unreachable
  errors, plus a backend `POST /automations/<id>/validate` as the authority before save.
- Free with the embed (don't rebuild): undo/redo, searchable step picker, variable chips with
  go-to-definition, JSON view/copy/paste modal, SVG/PNG canvas export, version diff (`DiffView`)
  for reviewing changes, and **live run visualization** — `deriveRunState` consumes a `RunEvent`
  stream; map automation-run WebSocket events onto it for per-node status highlighting during a
  real run.
- **Stretch — NL/agent bridge:** tramo's patch-based editing (`buildPatchToolSpec`, the same
  `apply_patch` surface the UI uses) is the natural upgrade path for the `nl_automation` mixin:
  the LLM edits the graph via typed patches instead of emitting raw step lists, and `DiffView`
  shows the user what the agent changed before accepting.

## Phases

| Phase | Status | Delivers | Proves |
|---|---|---|---|
| 1 | ✅ | `WorkflowDoc` storage + Kahn validation + Python topo executor + linear→graph compat shim + AST interpolation (`{{steps.*}}`) | graph engine runs tramo docs, no user migration |
| 2 | ✅ | control-flow nodes (`if`, `merge`, bounded `for-each`, `call-flow`) + DeviceKit node pack generated from the step-type registry + typed vars | branching / loops / composition; registry speaks tramo |
| 3 | ✅ | error contract: per-node `retry {count, delayMs, backoff}` + `runAfter: on-error/always` + compensation branches | flows fail safe, not silently |
| 4 | ✅ | triggers: manual + webhook (`/hooks/<token>`) + cron + event → one `enqueue_run` | external + internal events start runs |
| 5 | ✅ | parallel device fan-out — `for-each` device branches as concurrency-capped jobs | "run across the fleet", bounded |
| 6 | ✅ | embed tramo editor (Canvas/RightRail/useWorkflow, node-pack endpoint wired, validate, live run view); stretch: NL patches | operators author visually in our own editor |

Phases 1→2→3 sequential. Phase 4 needs 1 (+ plan 05/06). Phase 5 needs 1+2 (+ plan 05). Phase 6
needs 1+2 (the node pack must exist) — it is **no longer gated on plan 30** building canvas
foundations, since the canvas comes from tramo; it only needs a route to mount in.

## Decisions to make while executing (log, don't stop)

- **Doc format:** adopt `WorkflowDoc` natively (recommended) vs a DeviceKit-shaped model with a
  UI-boundary converter. Native — one source of truth, no drift, and we own the spec anyway.
- **Executor semantics:** tramo's TS runtime (`@tramo/runtime` `runner.ts`) is the *reference*
  for port/`runAfter`/template semantics; the Python engine implements only the subset DeviceKit
  uses. Backend is authoritative at runtime. Divergence between the two is the main long-term
  risk — when found, fix tramo at source (we own it) or the Python port, never fork semantics.
- **Expression evaluator:** AST allowlist (recommended) vs ServerKit's sandboxed `eval`. AST —
  device automations may be authored by less-trusted operators.
- **Loops:** explicit bounded `for-each` node (recommended) vs graph cycles. Bounded node —
  cycles make validation + termination hard, and tramo's editor assumes acyclic docs.
- **Migration:** compat shim (recommended, zero migration) vs converting stored automations. Shim.
- **tramo dependency mode:** npm install (recommended; it's published) vs `file:` link during
  development. If a tramo bug blocks a phase, fix it in `C:\Users\Juan\Documents\GitHub\tramo`
  and publish/link — never work around it in DeviceKit.

## Out of scope

- **A full BPMN/DSL.** The doc model is tramo's JSON; don't invent a second representation.
- **tramo's TS runtime in production.** DeviceKit never executes automations in JS; `@tramo/cli`
  / `@tramo/server` / `@tramo/runtime` are dev references only.
- **tramo's brand integration packs** (Gmail, Stripe, …). DeviceKit's node catalog is its own
  step-type registry + builtins; brand packs stay out of the bundle.
- **Arbitrary user-supplied Python nodes.** Node types come from the step-type registry (plan 15)
  and extensions; no free-form code execution on the host. (tramo's `js-transform` node is
  therefore **excluded** from the DeviceKit registry.)
- **Cross-automation shared mutable state.** Sub-automations pass context in/out; no global
  workflow variables beyond that.

## tramo source map (for implementers)

- Spec / doc model: `packages/spec/src/types.ts` (`WorkflowDoc`, `WorkflowNode` — `runAfter`,
  `retry`, `sensitive`/`requiredRole`; `WorkflowEdge` — `sourceHandle`/`targetHandle`)
- Kahn validation: `packages/spec/src/query.ts` (`topoSort`)
- Node definitions + catalogs: `packages/spec/src/nodes.ts` (`NodeDefinition`, `BUILTIN_NODES`,
  `mcpServerToNodeDefs` — the pattern for the DeviceKit node pack)
- Editor embed: `tramo/react` (`useWorkflow`, `Canvas`, `RightRail`), `tramo/styles.css`,
  `DiffView`, `deriveRunState` (live run), canvas export
- Agent patches (stretch): `packages/tramo-editor/src/agent` (`buildPatchToolSpec`, `apply_patch`)
- Reference executor semantics: `packages/runtime/src/runner.ts` (topo layers, loop planning,
  `runAfter` gating, retry)

## ServerKit source map (for implementers)

- Engine: `backend/app/services/workflow_engine.py` (Kahn walk, branch-gate
  `_is_node_reachable`, `_interpolate`, `_execute_node_with_retry`, `{success, critical}`)
- Service + model: `backend/app/services/workflow_service.py`, `backend/app/models/workflow.py`
- Triggers: `backend/app/api/workflows.py` (`webhook_trigger` `/hooks/<webhook_id>`,
  `enqueue_execution`), `WorkflowEventBus.emit` (event → `workflow.dispatch` job, cooldown)
- Fleet-node types to mirror: `agent_command` / `capability_gate` / `runtime_gate`
  (`workflow_engine.py` "Phase 4") — the bridge from a backend graph to on-device actions
- **Fix on port:** replace `eval` with an AST allowlist; run parallel branches as jobs (plan 05),
  not inline — ServerKit's executor is single-threaded + acyclic by design.
