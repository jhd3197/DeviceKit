# Plan 13 — AI Confirmation Gate & Tool Registry Safety

**Status:** proposed
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

1. `is_write` annotation + gate + confirm endpoint + SSE event + chat approval card.
2. Session modes + Profiles default + audit trail.
3. Extension tool binder integration; supervised self-heal option.

## Definition of done

Asking the device agent to "uninstall Instagram" produces an approval card, not an
uninstall; denying it makes the model acknowledge and continue; an `observe` session
never offers write tools to the model; every executed write tool is in the audit
history with who/what/when.
