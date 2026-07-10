# Plan 13 — AI Confirmation Gate & Tool Registry Safety

**Status:** ✅ shipped (phases 1–3). Deferred: per-tool custom result renderers (the
ServerKit `tool_renderers` idea — explicitly "Later" below).
**Inspired by:** ServerKit's `backend/app/services/ai_service.py` (ConfirmationGate),
`ai_tool_registry.py` (central registry, per-request filtering), `plugins_sdk/ai.py`
(`PluginToolBinder` with `is_write` flags)
**Depends on:** nothing hard — builds on the existing Prompture agent; 03 extends it to extensions

## Problem

DeviceKit's per-device AI agent (`prompture_agent.py`) exposes tools via
`build_device_tools()` — and those tools **act on real hardware**: taps, app installs,
shell commands, file operations. Today the LLM executes them unmediated. As the agent
grows more capable (and once extensions can contribute tools, plan 03), "the model
decided to `adb shell rm`" needs a human between decision and execution. ServerKit
solved exactly this for server-mutating tools.

## What ServerKit built

- **One central `AiToolRegistry`** (singleton): every tool registered with metadata —
  RBAC feature/level required, `is_write` flag. Built-in tools are `core__*`; plugin
  tools are `<slug>__*` (double-underscore because provider function-name rules forbid
  dots, 64-char limit — a portable gotcha).
- **Per-request filtering:** `list_for(user, mode)` — the model only *sees* tools the
  caller's permissions allow. A read-only session literally cannot call a write tool.
- **The confirmation gate:** when the model calls an `is_write=True` tool, the
  streaming worker **pauses on a gate**, emits a `pending_action` event describing the
  exact action, and blocks until the user approves/denies via a `/chat/confirm`
  endpoint. Approved → executes and streaming resumes; denied → the model gets a
  refusal result and continues.
- Guardrails around the loop: prompt-injection detector on inputs, PII redactor on
  outputs (worth noting, not necessarily v1 for DeviceKit).
- Frontend: the chat renders a pending-action card with Approve/Deny; plugin-supplied
  **tool renderers** customize how a given tool's output displays.

## Design for DeviceKit

### Backend

1. Annotate every tool in `build_device_tools()` with `is_write` + a category:
   - Read (no gate): screenshot, UI hierarchy, device properties, battery, app list
   - Write (gated): tap/swipe/type, install/uninstall app, `adb shell`,
     file write/delete, reboot, settings changes
2. `ConfirmationGate`: when a write tool is invoked, create a `pending_action`
   (id, device, tool, args, requested_at), broadcast it over the existing SSE channel,
   and block the tool call on an event/queue with a timeout (default deny on timeout).
   `POST /devices/<id>/agent/confirm {action_id, approve}` releases it. Prompture's
   tool-execution hook wraps this — if the current `ToolRegistry` API lacks a
   pre-execution hook, add one **in Prompture itself** (owned library — fix at the
   source per repo policy).
3. **Session modes:** `observe` (read tools only — filtered out of the tool list, not
   just blocked), `supervised` (write tools gated — default), `autonomous` (gate
   auto-approves, logged; for trusted automations/CI where a human isn't watching).
   Mode is a parameter on the agent session; per-device default in Profiles.
4. Audit every tool call (args, mode, who approved, result) — rides the
   `DeviceCommand` history from plan 07 or its own table (plan 01).
5. Extension AI tools (plan 03): `sdk.ai.tool(is_write=...)` binder namespaces them
   `<slug>__<name>`; extension write tools are **always** gated regardless of session
   mode — third-party code doesn't get autonomous hardware access.

### Frontend

1. The device AI chat (in `NodeDetail.jsx`) renders a pending-action card: tool name,
   human-readable summary ("Install `com.example.apk`"), args detail expander,
   Approve / Deny buttons, countdown to timeout.
2. Session-mode selector on the chat header; `observe` visually distinct.
3. Later: per-tool custom result renderers (screenshot tool → inline image), the
   ServerKit `tool_renderers` idea.

## Also applies to self-healing

`nl_automation.py`'s self-heal currently retargets a failed step and retries
autonomously. Under this framework a heal is a **write-ish decision**: in supervised
runs, surface "step failed — AI proposes tapping element X instead" for approval
(async: pause the run, notify via plan 06, resume on approval); in CI/autonomous
runs, keep today's auto-heal but log it through the same audit path.

## Phases

1. ✅ `is_write` annotation + gate + confirm endpoint + SSE event + chat approval card.
2. ✅ Session modes + Profiles default + audit trail.
3. ✅ Extension tool binder integration; supervised self-heal option.

### Implementation notes (as shipped)

- **Prompture (owned lib):** `ToolDefinition` gained a free-form `metadata` dict
  (`register(..., metadata=...)`), preserved through `filter/subset/exclude`. That's the
  seam the gate needs — no fork/workaround. (`prompture` commit `4eff308`.)
- **`build_device_tools(mixin, device_id, mode)`** now annotates every tool with
  `{is_write, category, label}`. Read tools (battery, properties, UI hierarchy, app list)
  run free; write tools (tap/swipe/type/press, open/uninstall app, `adb shell`, reboot)
  are wrapped so execution routes through `AgentGateMixin.gate_tool_call`. Write tools
  the model never should see in `observe` are filtered out of the registry entirely.
- **`AgentGateMixin`** (`mixins/agent_gate.py`): owns per-device session mode, the pending
  action registry (blocks the agent thread on a `threading.Event` with a settings-driven
  timeout → default-deny), SSE `pending_action` / `pending_action_resolved`, and the
  audit writer. Modes: `observe` (read-only), `supervised` (gate, default),
  `autonomous` (auto-approve + log). Extension write tools carry `always_gate` so they're
  gated even under autonomous.
- **Audit trail:** own table `agent_audit_log` (model + Alembic `b13a1c0de13`); every
  write decision (approved/denied/timeout/auto) persisted with who/what/when. Survives
  restart. `GET /devices/<id>/agent/audit`.
- **Endpoints:** `GET .../agent/pending`, `POST .../agent/confirm {action_id, approve}`,
  `GET|PUT .../agent/mode`, `GET .../agent/audit`. `get_agent_status` also carries `mode`
  + `pending_actions` so the existing 2s NodeDetail poll surfaces cards with no new SSE
  wiring.
- **Frontend:** NodeDetail AI panel gained a mode segmented-control and amber approval
  cards (summary, tool/source chips, args expander, live countdown, Approve/Deny).
- **Profiles:** new `agent_mode` field is the per-device default; settings add
  `ai.default_agent_mode` + `ai.gate_timeout_seconds`.
- **Extension tools (ph3):** `sdk.ai.tool` now takes `is_write` (`@sdk.ai.tool` or
  `@sdk.ai.tool(is_write=False)`), threaded through `_register_ai_tool` into the
  `_ext_ai_tools` tuple. Extension **write** tools are bound with `always_gate` so they're
  gated under every mode (never autonomous) and hidden under observe; read tools run free.
- **Self-heal (ph3):** `nl_automation` heals now re-execute through `gate_tool_call`
  (`source="self_heal"`): supervised runs pause on an approval card, autonomous auto-apply
  + audit (today's behavior, now logged), observe refuses. Guarded by
  `hasattr(self, "gate_tool_call")` so a gate-less composition falls back to direct
  execution. **Behavior note:** because the per-device default mode is `supervised`, a
  self-healing run on a device with no explicit mode now waits for approval — set the
  device's profile `agent_mode` to `autonomous` for unattended/CI runs.
- **Tests:** `backend/tests/test_agent_gate.py` (14: observe filtering, block/approve/deny,
  timeout default-deny, autonomous auto-approve, audit persistence across restart, HTTP
  endpoints, SDK binder `is_write`, extension read-free/write-gated/observe-hidden,
  observe direct-write deny) + a Prompture `TestMetadata` suite.

### Deferred

- Per-tool custom result renderers (screenshot tool → inline image), the ServerKit
  `tool_renderers` idea — marked "Later" in the frontend section above.
- Live device / provider-key verification: the gate, modes, audit, and endpoints are
  proven by the test suite against fake tools; exercising a real LLM deciding to
  `uninstall_app` on a physical phone needs a Prompture provider key + a connected device.

## Definition of done

Asking the device agent to "uninstall Instagram" produces an approval card, not an
uninstall; denying it makes the model acknowledge and continue; an `observe` session
never offers write tools to the model; every executed write tool is in the audit
history with who/what/when.
