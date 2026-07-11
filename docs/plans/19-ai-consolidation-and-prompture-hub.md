# Plan 19 — AI Provider Consolidation + Prompture Hub Integration

**Status:** ✅ shipped (2026-07-11) — all 4 phases
**Inspired by:** DeviceKit already standardized its AI on **Prompture** (Phase 16) — the
per-device conversational agent, NL automation, visual-diff analysis, and debug-bundle
summaries all go through `prompture`. But two loose ends remain: a legacy *direct*
provider path still lingers in `agent.py`, and there's a better place to put provider
keys than DeviceKit's own `.env` — **[`prompture-hub`](https://github.com/jhd3197/prompture-hub)**,
the self-hosted LLM gateway that holds real provider keys server-side and hands out
scoped, metered, revocable keys.
**Depends on:** Phase 16 (Prompture — shipped), plan 12 settings/AI pane (shipped). Soft:
03 (`llm` extension permission — the biggest beneficiary).

## The questions this plan answers

- **"Am I accidentally depending on OpenAI directly?"** Yes, in one place. `agent.py`
  still has the pre-Prompture path: `AI_PROVIDER` env + `_ask_openai()` (`from openai
  import OpenAI`) and `_ask_anthropic()` (raw Anthropic SDK), with regex JSON extraction
  (`backend/devicekit/mixins/agent.py:9,226,258`). Everything *else* moved to Prompture
  in Phase 16; this path is the straggler. Consolidating it removes DeviceKit's only
  direct provider-SDK dependency — after this, provider choice lives entirely in
  Prompture's driver registry, exactly as you want.
- **"Can I route AI through Prompture Hub instead of putting provider keys in DeviceKit?"**
  Yes — and that's the point of the hub. Today DeviceKit stores raw provider keys in the
  settings table and pushes them into `os.environ` for Prompture to read
  (`mixins/settings.py:138`, `ai.provider_keys`). With the hub, DeviceKit stores **one
  hub key** (`ph_...`) and points Prompture's OpenAI-compatible driver at the hub's
  `/v1` endpoint. The real `OPENAI_API_KEY` never enters DeviceKit at all.
- **"Can DeviceKit detect if the hub is running and make setup easy?"** Yes — the hub has
  a `/health` endpoint and a `/v1/models` list. DeviceKit's AI settings pane can probe
  the configured hub URL, show a green/red status, list the models the hub allows, and
  link straight to `pip install prompture-hub` and the hub dashboard
  (`http://localhost:1984/app/`).
- **"What about extensions that want AI?"** This is the sleeper win. Extensions can hold
  the `llm` permission and call `sdk.ai(slug)` — but on direct-key config that means
  third-party code runs against *your* provider key with no cap. Route extension AI
  through the hub and each extension gets its **own** hub key with an allowed-model
  whitelist and a daily spend cap, revocable instantly. That turns "extensions are not
  sandboxed" (a real limitation, per the plan-16 ADRs) into "extensions can't run up an
  unbounded LLM bill or see your provider secrets."

## Part 1 — Consolidate on Prompture (remove the direct path)

**Retire `agent.py`'s legacy provider methods.** `_ask_anthropic`/`_ask_openai` +
`AI_PROVIDER` + `extract_json_from_text` predate the Prompture agent
(`mixins/prompture_agent.py`), which already does structured `DeviceAction` output via a
`ToolRegistry`. Point whatever still calls the legacy path at the Prompture agent, then
delete the direct-SDK methods.

- Verify call sites first: if `_ask_*` is dead post-Phase-16, this is pure deletion; if a
  code path still uses it, migrate that path to `Conversation.ask(...)` with the
  `DeviceAction` schema (the pattern `prompture_agent.py` already uses).
- Drop `openai` (and the direct `anthropic` SDK, if unused elsewhere) from
  `backend/requirements.txt`. Prompture pulls whatever provider driver it needs; DeviceKit
  shouldn't import provider SDKs directly.
- **One-way door check:** confirm nothing outside `agent.py` imports `openai`/`anthropic`
  (grep showed only `agent.py:260`). If clean, the direct dependency is gone for good.

Outcome: a single AI path (Prompture), one place that picks providers (Prompture's
registry, configured via settings), zero direct provider-SDK imports.

## Part 2 — Prompture Hub as an optional AI backend

**A backend selector in settings.** Extend the AI settings schema
(`mixins/settings.py`, currently `ai.default_model` / `ai.model_overrides` /
`ai.provider_keys`) with:

```
ai.backend        = "direct" | "hub"     # default "direct" (unchanged behavior)
ai.hub.url        = "http://localhost:1984"
ai.hub.key        = "ph_..."             # secret, masked like provider_keys
```

- `direct` (default): today's behavior — provider keys in env, Prompture uses them. No
  change for anyone not opting in.
- `hub`: DeviceKit configures Prompture to use an **OpenAI-compatible driver** with
  `base_url = {ai.hub.url}/v1` and `api_key = {ai.hub.key}`. The hub exposes
  `/v1/chat/completions` and `/v1/models` as a drop-in OpenAI surface (README confirms),
  plus `/v1/extract` for Prompture-native JSON-schema structured output and
  `/v1/conversations` for resumable sessions — which map cleanly onto how DeviceKit
  already uses Prompture (`Conversation`, structured `DeviceAction`, per-device history).

**Boot + save wiring** mirrors the existing key-apply seam: on boot and on settings save,
if `ai.backend == "hub"`, set the hub driver config instead of pushing provider keys into
`os.environ`. `ai.hub.key` is a secret (add to `_SECRET_KEYS`, masked in `to_dict`).

**Validate the tricky bits against the hub, don't assume:** DeviceKit leans on tool-use
(ToolRegistry) and structured Pydantic output. Confirm both survive the hub's
OpenAI-compat endpoint; the hub is *built with* Prompture so they should, but
`prompture-hub` is v0.0.x (no SSE streaming yet per its roadmap) — if any DeviceKit AI
feature streams, note it degrades to non-streaming through the hub, or keep that feature
on `direct`. Log the finding either way.

## Part 3 — Detection, health & setup UX

In the Settings → AI pane (plan 12), when `ai.backend == "hub"`:

- **Health probe** — `GET {hub.url}/health` (and `/v1/models` for the allowed-model
  list). Show a green/red indicator like the agent Test-Connection button (Phase 10
  pattern): "Hub reachable · 4 models · spend cap $X/day" or "Hub not reachable at
  localhost:1984."
- **Model picker sourced from the hub** — populate `ai.default_model` / overrides from
  `/v1/models` so users pick from what their hub key is *allowed* to use, not a
  free-text field that 403s at call time.
- **Setup links when unreachable** — inline help: `pip install prompture-hub`, a link to
  the dashboard (`http://localhost:1984/app/`), and a one-liner on creating a hub key.
  The "run it natively, not in Docker, so it can see localhost model servers" caveat from
  the hub README is worth surfacing.
- **Backend health endpoint** — a small `GET /ai/hub/health` proxy route so the frontend
  probes the hub through DeviceKit's backend (avoids CORS and keeps the hub URL
  server-side).

## Part 4 — Per-extension hub keys (the security payoff)

Tie the hub into the extension `llm` permission (`devicekit_sdk/permissions.py`,
`sdk.ai(slug)`):

- When `ai.backend == "hub"`, an extension declaring `llm` can be issued its **own** hub
  key via the hub's `/admin/*` API (create-key, gated by `HUB_ADMIN_TOKEN` held only by
  DeviceKit's backend), scoped to an allowed-model whitelist and a daily spend cap set at
  install/consent time.
- `sdk.ai(slug)` then routes that extension's LLM calls through *its* hub key, not the
  host's. Revoke the extension → revoke its hub key → it's locked out instantly, no
  provider-key rotation.
- On `direct` backend this is unavailable; extensions fall back to the host key (today's
  behavior) or the `llm` permission simply can't be satisfied — a decision to make and
  log. This is exactly the "contain untrusted extension code" story the plan-16 security
  ADR wants but couldn't offer before.

## Phases

| Phase | Delivers | Notes | Status |
|---|---|---|---|
| 1 | Retire `agent.py` legacy `_ask_*` + `AI_PROVIDER`; drop `openai`/direct-`anthropic` deps | Single Prompture path; verify call sites first | ✅ |
| 2 | `ai.backend` setting + hub OpenAI-compat driver wiring (boot + save) + masked `ai.hub.key` | Opt-in; `direct` stays default | ✅ |
| 3 | Hub health probe + `/ai/hub/health` route + model picker from `/v1/models` + setup links in AI pane | The detection + easy-setup UX | ✅ |
| 4 | Per-extension hub keys via `/admin/*` + `sdk.ai(slug)` routing + consent-time cap/whitelist | The extension security win | ✅ |

**Phase 2 notes (the "validate, don't assume" findings):** the hub's OpenAI-compat
`/v1/chat/completions` (v0.0.2 source, verified) accepts **no `tools` or
`response_format` fields** and flattens messages to plain text — so through the hub,
Prompture's ToolRegistry degrades to its *simulated* tool path and structured output to
prompted-repair extraction; vision content is unavailable. SSE **streaming IS
implemented** hub-side (the README roadmap saying otherwise is stale). `HubDriver`'s
capability flags encode exactly this so Prompture degrades gracefully instead of
silently dropping tool calls. `OpenAIDriver` in Prompture had no `base_url` hook — fixed
at the source (prompture commit `e0d83b2`: `base_url` param + `OPENAI_BASE_URL` env)
rather than worked around here. Hub routing re-prepends the provider prefix so the hub
receives full `provider/model` ids, matching its `/v1/models` catalog. Wiring lives in
`backend/devicekit/ai_backend.py` + `mixins/settings.py`; covered by
`tests/test_ai_backend.py`.

**Phase 4 notes:** `sdk.ai(slug)` grew the LLM call surface (`ask` / `conversation`,
gated on the `llm` permission) backed by `ExtensionAiMixin.extension_ai_*`. On the hub
backend each `llm` extension gets its own key at install (revoked at uninstall), scoped
by the manifest's `llm_allowed_models` / `llm_daily_cap_usd` (default $1/day) — the
"consent-time" cap is manifest-declared and shown on the consent card like every other
manifest claim; there's no separate cap-editing UI (logged decision). `HUB_ADMIN_TOKEN`
is env-only, never a setting. Key records live in the server-managed, masked
`ai.hub.extension_keys` setting (PUT /settings refuses writes to it). Decisions per plan:
on `direct` (or hub without admin token) extension calls fall back to host credentials
with a warning — isolation requires the hub; keys are revoked at uninstall, not disable
(the status guard already stops a disabled extension from running). Verified live:
scoped key issued via `/admin/keys`, `sdk.ai().ask()` answered through the extension's
own key against local Ollama, off-whitelist model 403'd, revoke → instant 401. Also
fixed a repo-wide quirk found while testing: Alembic's `fileConfig` was silently
disabling every logger created before boot-time migrations (`alembic/env.py` now passes
`disable_existing_loggers=False`).

**Phase 3 notes:** verified live against a real hub + local Ollama: `GET /ai/hub/health`
through DeviceKit reported reachable + the key-scoped 750-model catalog, and a real
completion ran DeviceKit wiring → hub → `ollama/qwen2.5:1.5b` (off-whitelist models 403,
usage metered per key). The hub's `/v1/models` is slow on its first call after hub boot
(catalog built lazily) — the probe gives it a longer timeout than `/health`. The health
line shows "N models allowed" (no spend-cap figure: the hub exposes caps only via the
admin API, not to key holders). Fixed a hub boot-blocker at the source while testing
(prompture-hub commit `e019f2e`: two `status_code=204` routes crashed FastAPI at import).
The health status card also documents `pip install prompture-hub`, the dashboard link,
and the run-natively caveat when unreachable.

**Phase 1 deviation note:** `AgentMixin` was already dead post-Phase-16 — nothing imported
`mixins/agent.py` (`client.py` composes `PromptureAgentMixin`), so this was pure deletion:
the file, plus `extract_json_from_text`/`remove_json_extras` in `tools.py` (agent.py was
their only caller). `openai`/`anthropic` were never in `requirements.txt` (they were lazy
imports inside the dead methods), so there was nothing to drop — the deletion itself
removed DeviceKit's last direct provider-SDK imports.

Phase 1 is independent and can land first (pure consolidation). Phases 2→3 are
sequential; phase 4 depends on 2.

## Decisions to make while executing (log, don't stop)

- **Hub required vs optional:** keep it **optional** (`direct` default). DeviceKit must
  run with no hub for the solo/local user. Don't turn the hub into a hard dependency.
- **Structured output route:** OpenAI-compat `/v1/chat/completions` (max compatibility)
  vs Prompture-native `/v1/extract` for the JSON-schema features. Prefer letting Prompture
  pick; only special-case if extract-over-HTTP gives better structured reliability.
- **Extension fallback on `direct`:** host key vs refuse `llm`. Lean host-key-with-warning
  for continuity, but document that per-extension isolation requires the hub.

## Out of scope

- **Building or extending prompture-hub itself.** It exists (v0.0.2, on PyPI). This plan
  *integrates* it; hub features (SSE streaming, embeddings, key-creation UI) are the
  hub's own roadmap.
- **Bundling the hub inside DeviceKit.** Users install/run it separately (native, per its
  README). DeviceKit detects and points at it.
- **Multi-user / hosted hub deployment.** The hub is solo/localhost today; DeviceKit's
  integration targets that and inherits multi-user when the hub gets there.
