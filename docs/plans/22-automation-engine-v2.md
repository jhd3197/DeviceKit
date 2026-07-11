# Plan 22 — Automation Engine v2: DAG + Triggers

**Status:** proposed
**Inspired by:** plan 18 calls the current engine "the linear automation engine" — an ordered list
of steps with no branching, loops, parallelism, or sub-flows. ServerKit's
`backend/app/services/workflow_engine.py` is the upgrade path *already built and shipped*:
workflows are a nodes+edges graph executed by a **Kahn topological walk**, with a `logic_if`
branch-gate (`_is_node_reachable` only runs nodes fed by an *active* branch), a per-node
`{success, critical}` contract (critical aborts the run, non-critical logs + continues), per-node
retry (`retryCount`/`retryDelay` in `_execute_node_with_retry`), and `${node.field}` /
`{{context.field}}` interpolation (`_interpolate`). And `backend/app/api/workflows.py` funnels
**four trigger types — manual / webhook / cron / event —** through one `enqueue_execution`,
including a public `POST /hooks/<webhook_id>` where the id *is* the token, plus
`WorkflowEventBus.emit` turning internal events into automations (60s per-workflow cooldown).
**Depends on:** 05/25 (jobs/queue — each run executes as a cancellable, restart-safe job; the
substrate for real parallel fan-out), 15 (step-type registry — the node executors), 06
(notification bus — the event-trigger source). Soft: 30 (frontend foundations — the graph
builder), 20 (scoped webhook tokens).

## Honest limitations to copy *around* (from reading the source)

ServerKit's engine is a great model, but three of its properties are *not* what a device fleet
wants — so port the shape, fix these:

1. **It executes sequentially** even though the graph models fan-out (`while ready: popleft`, single
   thread). For true parallel *device* fan-out, run per-device branches as **separate jobs** (plan
   05) — don't inline them.
2. **It's acyclic** — cycles are rejected at validate time. Loops (retry-N, for-each-device) need an
   explicit **bounded-iteration node**, not graph cycles.
3. **Conditions use a sandboxed `eval()`** (`__builtins__={}` + a whitelist). For fleet operators
   who author automations, prefer a small **AST-allowlist expression evaluator** over raw `eval`.

## The questions this plan answers

- **"Can a flow branch on a result?"** Yes — a `logic_if` node emits a `true`/`false` branch and
  edges carry a `sourceHandle`; only nodes fed by the active branch run.
- **"Can it run across 50 devices at once, or retry, or call another automation?"** Yes — bounded
  `for_each` over a device list / FQL result, per-device branches dispatched as concurrency-capped
  jobs, per-node retry/backoff, and a `sub_automation` node.
- **"Can something *outside* DeviceKit start an automation?"** Yes — a per-automation webhook URL
  (the id is the token), plus internal device events (offline, low battery, geofence) driving the
  same run path. All four trigger types funnel through one `enqueue_run`.

## Part 1 — The graph model + executor (with a compat shim)

- Store `nodes` + `edges` JSON on the `Automation` row. Validate with Kahn in-degree tracking
  (reject cycles with a clear "cycle detected at node X"). Execute as a topological walk.
- **Compatibility shim:** an existing linear automation becomes a straight-line graph
  automatically — no user migration, the old step list still runs.
- Per-node contract: `{success, critical}`; `critical` aborts, non-critical logs + continues.
  `${node.field}` / `{{context.field}}` interpolation via the AST evaluator (not `eval`).

## Part 2 — Control-flow nodes

- `logic_if` — 2-way branch-gate (extend to `switch` later if needed).
- `for_each` — **bounded** iteration over a device list or FQL result; each iteration is a branch.
- `sub_automation` — call another automation as a node (cycle-guarded).
- Typed step variables so a downstream node can consume `${serp.top_url}` etc. (the plan-17
  `_store_step_var` flattening already prototypes this).

## Part 3 — Error & retry contract

- Per-node retry (`retryCount` / `retryDelay`, backoff) and an `on_failure: abort | continue` edge.
- An optional **compensation node** for a failed branch (ServerKit only has ad-hoc rollback — this
  makes it first-class).

## Part 4 — Triggers (one `enqueue_run` for all four)

- **manual** (today) + **webhook** (`POST /hooks/<token>`, token *is* auth, wraps the POST body as
  run `context`) + **cron/interval** (plan 05 `ScheduledJob`) + **event** (plan 06 bus →
  `automation.dispatch` job → match active event-triggered automations by event type, per-automation
  cooldown to prevent storms).
- The webhook trigger is DeviceKit's answer to "external events can't start automations" — it and
  the event trigger are the reason this plan absorbs the inbound-webhook idea rather than a separate
  plan.

## Part 5 — Parallel device fan-out via jobs

- The one thing ServerKit's inline engine *can't* do. A `for_each`-over-devices node dispatches one
  **job per device branch** on the queue (plan 05), concurrency-capped, results collected back into
  the parent run. This is where "run this automation across the whole fleet" becomes real and
  bounded (echoes plan 24's `fleet_sweep` discipline: bounded pool, per-device timeout, one slow
  device never stalls the run).

## Part 6 — Frontend graph builder

- A node canvas (React-Flow-style) to author graphs, wired into the plan-30/31 frontend surface:
  palette of node types, edge drawing, per-node config, a dry-run/validate button that surfaces
  cycle + unreachable-node errors before save.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | nodes+edges model + Kahn validation + topo executor + linear→graph compat shim + AST interpolation | graph engine runs, no user migration |
| 2 | control-flow nodes: `logic_if`, bounded `for_each`, `sub_automation`, typed vars | branching / loops / composition |
| 3 | error contract: per-node retry/backoff + `on_failure` edge + compensation node | flows fail safe, not silently |
| 4 | triggers: manual + webhook (`/hooks/<token>`) + cron + event → one `enqueue_run` | external + internal events start runs |
| 5 | parallel device fan-out — `for_each` device branches as concurrency-capped jobs | "run across the fleet", bounded |
| 6 | frontend graph builder (canvas, validate, dry-run) | operators author visually |

Phases 1→2→3 sequential. Phase 4 needs 1 (+ plan 05/06). Phase 5 needs 1+2 (+ plan 05). Phase 6
last (needs the model + plan 30).

## Decisions to make while executing (log, don't stop)

- **Expression evaluator:** AST allowlist (recommended) vs ServerKit's sandboxed `eval`. Choose AST
  — device automations may be authored by less-trusted operators.
- **Loops:** explicit bounded `for_each` node (recommended) vs allowing graph cycles. Bounded node —
  cycles make validation + termination hard.
- **Migration:** compat shim (recommended, zero migration) vs converting stored automations. Shim.

## Out of scope

- **A full BPMN/DSL.** Extend the existing JSON step model into a graph; don't replace it.
- **Arbitrary user-supplied Python nodes.** Node types come from the step-type registry (plan 15)
  and extensions; no free-form code execution on the host.
- **Cross-automation shared mutable state.** Sub-automations pass context in/out; no global
  workflow variables beyond that.

## ServerKit source map (for implementers)

- Engine: `backend/app/services/workflow_engine.py` (Kahn walk, `logic_if`,
  `_is_node_reachable`, `_interpolate`, `_execute_node_with_retry`, `{success, critical}`)
- Service + model: `backend/app/services/workflow_service.py`, `backend/app/models/workflow.py`
- Triggers: `backend/app/api/workflows.py` (`webhook_trigger` `/hooks/<webhook_id>`,
  `enqueue_execution`), `WorkflowEventBus.emit` (event → `workflow.dispatch` job, cooldown)
- Fleet-node types to mirror: `agent_command` / `capability_gate` / `runtime_gate`
  (`workflow_engine.py` "Phase 4") — the bridge from a backend graph to on-device actions
- **Fix on port:** replace `eval` with an AST allowlist; run parallel branches as jobs (plan 05),
  not inline — ServerKit's executor is single-threaded + acyclic by design.
