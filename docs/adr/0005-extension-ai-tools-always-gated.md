# ADR 0005 — Extension-contributed AI tools are always gated

- **Status:** Accepted
- **Recorded in:** [plan 13 — AI confirmation gate](../plans/13-ai-confirmation-gate.md);
  [ROADMAP Phase 33](../../ROADMAP.md).

## Context

The per-device Prompture agent's tools act on real hardware — taps, app install/uninstall,
`adb shell`, file writes, reboot. Plan 13 introduced a confirmation gate with three **session
modes**: `observe` (read-only — write tools are hidden), `supervised` (write tools block for
approval — the default), and `autonomous` (the gate auto-approves and logs, for trusted
automations/CI). Plan 03 lets **extensions** contribute AI tools, namespaced `<slug>__<name>`.

## Decision

An extension-contributed AI tool that mutates the device (`sdk.ai.tool(is_write=True)`) is **always**
routed through the confirmation gate — bound with an `always_gate` flag so it is **never
auto-approved, even in `autonomous` mode**, and hidden entirely under `observe`. Extension **read**
tools (`is_write=False`) run free.

## Rationale — the threat model

**Third-party code doesn't get autonomous hardware access.** Core `core__*` write tools may
auto-approve under `autonomous` because they are first-party and trusted. Extension tools are
third-party — and, per [ADR 0001](0001-in-process-extensions.md), they run in-process and
unsandboxed. So even a trusted-mode session must keep a human between the model's decision and an
extension tool executing on a physical device. The concern "the model decided to `adb shell rm`" is
compounded by "…via untrusted extension code."

## Consequences

- Enforced in `build_device_tools` / `AgentGateMixin.gate_tool_call`; the SDK binder threads
  `is_write` through `_register_ai_tool` and marks extension write tools `always_gate`.
- Every write decision (`approved` / `denied` / `timeout` / `auto`) is persisted to the
  `agent_audit_log` table (survives restart).
- Self-heal decisions route through the same gate.
- Covered by `backend/tests/test_agent_gate.py` (extension read-free, write-gated, observe-hidden).

## Alternatives considered

- **Treat extension tools like core tools** (honor session mode, i.e. auto-approve under
  `autonomous`) — rejected: it would hand unattended hardware access to third-party code.
- **Block extension tools entirely** — rejected: read tools are safe and useful; write tools are
  gated, not forbidden.
