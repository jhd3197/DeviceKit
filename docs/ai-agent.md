# AI Agent

DeviceKit's AI layer turns each device into a **conversational agent** and weaves AI into the
automation engine. Everything runs through [Prompture](https://pypi.org/project/prompture/) — one
multi-provider abstraction — so a device can be driven by Claude, GPT-4, Groq, Ollama, or Google by
changing a model string. There are no direct provider SDK calls in the live path.

This doc describes what's **shipped**. It supersedes the original design note
[`prompture_integration.md`](../prompture_integration.md) (kept as historical design); where the
two differ, this is right — the shipped system added the confirmation gate, session modes, NL
automation, and self-healing that the design doc predates.

Three surfaces use the AI layer:

1. **The per-device agent** — a persistent conversation that can call device actions as tools.
2. **NL automation** — generate / refine / explain automations from plain English, plus self-heal.
3. **Visual regression** — AI adjudication of screenshot diffs (see the
   [README](../README.md#visual-regression-testing)).

---

## The per-device agent

`PromptureAgentMixin` (`backend/devicekit/mixins/prompture_agent.py`) runs one **`DeviceConversation`**
per device — a Prompture `Conversation` wrapping a `ToolRegistry`, a `UsageSession` (token/cost
tracking), and `DriverCallbacks` (observability), with `max_tool_rounds=10`. The system prompt is
built from the device's profile (personality, niche, interests, browsing style).

- **Memory persists.** Stopping the agent does **not** delete the conversation — restart it and the
  device "remembers." Clear it explicitly with `DELETE /devices/<id>/conversation`.
- **Tool use, not JSON parsing.** The LLM calls device actions directly as tools; one `ask()` can
  chain `open_app → tap → type_text → done` in a single turn. There is no per-cycle JSON schema to
  parse.
- **Per-device cost.** `UsageSession` accrues prompt/completion tokens, cost, and call counts,
  surfaced at `GET /devices/<id>/agent/usage` and aggregated into the dashboard's Fleet AI Cost.

### The tools

`build_device_tools(mixin, device_id, mode)` registers two classes of tool, split by whether they
mutate the device:

| Kind | Tools | Gated? |
| --- | --- | --- |
| **Read** | `get_battery`, `device_properties`, `get_ui_hierarchy`, `list_installed_apps` | No — run free |
| **Write** | `tap`, `swipe`, `type_text`, `press_key`, `open_app`, `uninstall_app`, `adb_shell`, `reboot_device` | Yes — through the confirmation gate |

The model always sees each tool's true signature; only *execution* of a write tool is mediated by
the gate.

### Model selection

Each device can run a different model, in Prompture's `provider/model` form. The default resolves in
order: **explicit `model_name` arg → the device profile's `model_name` → the saved `ai.default_model`
setting → `PROMPTURE_DEFAULT_MODEL`** (default `claude/claude-sonnet-4-20250514`). Switch a running
agent's model with `PATCH /devices/<id>/agent/model`.

| Provider | `model_name` |
| --- | --- |
| Claude | `claude/claude-sonnet-4-20250514` |
| OpenAI | `openai/gpt-4o` |
| Groq | `groq/llama-3.1-70b-versatile` |
| Ollama (local) | `ollama/llama3.1:8b` |
| Google | `google/gemini-2.0-flash` |

---

## The confirmation gate

A human sits between the LLM and the hardware. `AgentGateMixin`
(`backend/devicekit/mixins/agent_gate.py`) mediates every **write** tool call according to the
device's **session mode**:

| Mode | Write tools |
| --- | --- |
| `observe` | **Hidden** from the model entirely — read-only. |
| `supervised` *(default)* | **Block** on the gate awaiting human approve/deny. |
| `autonomous` | Core write tools **auto-approve** (and are audited). **Extension tools never auto-approve.** |

**How a supervised call flows:** the gate creates a pending action, broadcasts an SSE
**`pending_action`** event (an approval card appears in the NodeDetail chat), and blocks. The
operator resolves it via `POST /devices/<id>/agent/confirm` (`{action_id, approve}`), which fires a
**`pending_action_resolved`** SSE event. **Timeout is default-deny** — if no one responds within
`ai.gate_timeout_seconds` (default 120s), the call is denied and the model reads a `DENIED:` string.

**The mode** resolves per device: a live session override → the device profile's `agent_mode` → the
`ai.default_agent_mode` setting (default `supervised`). Read it / set it at
`GET`/`PUT /devices/<id>/agent/mode`.

**Audit trail.** Every write decision (`approved` / `denied` / `timeout` / `auto`) is persisted to
an `AgentAuditLog` row (survives restart), readable at `GET /devices/<id>/agent/audit`. Read tools
are neither gated nor audited, by design.

### Extension AI tools are always gated

An AI tool contributed by an extension (`sdk.ai.tool`) is **always** routed through the gate when it
mutates the device — even in `autonomous` mode — and hidden in `observe`. Third-party code never
gets unattended hardware access. This is [ADR 0005](adr/0005-extension-ai-tools-always-gated.md);
see the [SDK Reference](extensions/sdk-reference.md#ai) for how `is_write` drives it.

---

## NL automation & self-healing

`NLAutomationMixin` (`backend/devicekit/mixins/nl_automation.py`) is the bridge between the AI layer
and the [automation engine](../README.md#automation-engine). It uses Prompture conversations (no
tools) primed with the full step-type schema, so generated steps are valid.

| Endpoint | Does |
| --- | --- |
| `POST /automations/generate` | `{description, device_id?}` → generated steps + explanation. |
| `POST /automations/refine-step` | `{step, instruction, device_id?}` → a rewritten step (preserves id/order). |
| `GET /automations/<id>/explain` | Plain-English summary of what an automation does. |
| `GET /devices/<id>/ui-hierarchy` | The accessibility tree (agent `/ui/dump`, uiautomator2 fallback). |

**Self-healing.** When a UI-targeting step fails — one of `tap_by_text`, `tap_by_resource_id`,
`wait_for_element`, `assert_element` — and the run was started with `self_heal: true`
(`POST /automations/<id>/run`), the engine captures the current UI hierarchy, asks the LLM to
re-locate the target, and retries. **The healed action is applied through the same confirmation
gate**: supervised pauses for approval, autonomous auto-applies, observe refuses. A healed step is
badged in the run detail, and an `automation.run.healed` notification fires.

---

## Endpoints

Agent control (`backend/devicekit/routes/ai_agent.py`):

| Method & path | Purpose |
| --- | --- |
| `GET /agent/status` · `GET /agent/<id>/status` | Agent state (+ usage, model, mode, pending actions). |
| `POST /agent/<id>/start` · `POST /agent/<id>/stop` | Start/stop the per-device agent. |
| `POST /agent/<id>/command` | Enqueue a natural-language command (`{command, priority}`). |
| `GET /agent/<id>/commands` · `GET /agent/<id>/logs` | Command queue / action log. |
| `GET /devices/<id>/conversation/history` · `DELETE /devices/<id>/conversation` | Read / clear memory. |
| `GET /devices/<id>/agent/usage` | Tokens, cost, call count. |
| `PATCH /devices/<id>/agent/model` | Switch model (`{model_name}`). |
| `GET /devices/<id>/agent/mode` · `PUT …/mode` | Read / set session mode. |
| `GET /devices/<id>/agent/pending` · `POST …/confirm` | List / resolve pending write actions. |
| `GET /devices/<id>/agent/audit` | The write-tool audit trail. |

---

## Configuration

AI needs a Prompture provider key. Set it in `.env` **or** — the shipped way — in the Settings → AI
pane, which writes to a durable settings table and pushes provider keys into the environment so
Prompture picks them up live.

```bash
# .env
PROMPTURE_DEFAULT_MODEL=claude/claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY / OLLAMA_HOST as needed
```

Durable AI settings (Settings → AI): `ai.default_model`, `ai.model_overrides`
(`{generation, self_heal, analysis}`), `ai.provider_keys`, `ai.default_agent_mode` (`supervised`),
`ai.gate_timeout_seconds` (`120`). Without a provider key, AI routes return a clear error — the rest
of DeviceKit runs fine without one.

> **Honesty note:** a legacy `backend/devicekit/mixins/agent.py` with direct `anthropic`/`openai`
> calls still exists in the tree but is **not wired into `Client`** and is unused — it's slated for
> removal in [plan 19](plans/19-ai-consolidation-and-prompture-hub.md). The live path is 100%
> Prompture.
