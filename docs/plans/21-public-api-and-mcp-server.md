# Plan 21 — Public API `/api/v1`, Scoped Keys, OpenAPI & MCP Server

**Status:** proposed
**Inspired by:** ServerKit serves everything under `/api/v1` with **dual auth** — session/JWT for
the UI, `X-API-Key: sk_…` for machines — and **auto-generates** its OpenAPI 3.0 spec by walking
the Flask `url_map` (`backend/app/services/openapi_service.py`: blueprint → tag, view docstring →
summary, both `BearerAuth` + `ApiKeyAuth` schemes; zero hand-maintained spec). Programmatic callers
are gated by a `require_scope` decorator that is a **pass-through for session/JWT requests** and
only enforces scopes when the caller used an API key (`middleware/api_scope_middleware.py`) — so one
endpoint safely serves both the UI and machines. **Neither ServerKit nor DeviceKit exposes itself
as an MCP server** — that's the greenfield differentiator: a thin MCP wrapper over the scoped API
lets Claude enumerate devices, target groups by FQL, and invoke agent actions with per-tool scope
gating. (`docs/MCP_SERVER_ACCESS.md` in ServerKit is a red herring — an SSH-for-Claude howto, not a
self-exposed server.)
**Depends on:** **20 (HARD** — a public API needs per-key scopes + identity; without it the API is
either fully open or fully closed), 02 (blueprints — the `url_map` the generator walks), 13 (device
tools already annotated read vs write — the MCP tool gate reuses that annotation). Soft: 10
(command palette already models "actions" that map to MCP tools).

## The questions this plan answers

- **"Can an external system drive DeviceKit?"** Not today — it's driven only by its own frontend +
  agents. This mounts a stable, versioned `/api/v1` with `dk_` key auth so CI, scripts, and other
  tools can list devices, run automations, and read fleet state.
- **"Can Claude drive the fleet?"** Yes — the payoff. An MCP server over the scoped API turns every
  curated capability into an MCP tool. Claude enumerates devices, runs an FQL query, triggers an
  automation, or sends a command — each gated by the key's scopes, and each **write tool still flows
  through the plan-13 confirmation gate** so a human approves hardware-touching actions.
- **"Do I have to hand-maintain an API spec?"** No — generate OpenAPI from the blueprint `url_map`,
  the same way ServerKit does. One `/api/v1/openapi.json`, always in sync.

## Part 1 — Versioned `/api/v1` + dual auth + `require_scope`

- Mount a `/api/v1` blueprint surface (reuse the existing route modules; the plan-02 refactor
  already splits them per feature). Every route resolves a principal via the plan-20 resolver.
- `require_scope("devices:read")` decorator: **pass-through when the request is session-authed**
  (the UI already passed RBAC), enforce the scope only when a `dk_` key was used. This is the trick
  that lets one endpoint serve UI + machines without duplicate handlers.
- **Device-oriented scope catalog:** `devices:read`, `devices:command`, `automations:read`,
  `automations:run`, `metrics:read`, `extensions:admin`, `fleet:admin`, plus `*` master and
  `<feature>:*` wildcards (matcher shared with plan 20's key scopes).

## Part 2 — Auto-generated OpenAPI

- Walk the Flask `url_map`: blueprint name → tag, view docstring → summary/description, declare
  both `BearerAuth` (session) and `ApiKeyAuth` (`dk_` header) security schemes, infer request/response
  shapes from the existing response envelopes.
- Serve `/api/v1/openapi.json` + a rendered docs page (or feed the existing docs site, plan 16).
  No hand-maintained spec file — the generator is the source of truth.

## Part 3 — The MCP server (the differentiator)

- A thin MCP server (stdio **and** streamable-HTTP transports) that authenticates with a `dk_` key
  scoped to exactly the tools it may call, and exposes a **curated** tool set — not the whole API:
  - read: `list_devices`, `get_device_state`, `query_fleet(fql)`, `list_automations`, `get_metrics`
  - write: `run_automation`, `send_command`, `provision_app` (plan 18) — each mapped to a scope
- **Reuse the plan-13 read/write annotation:** MCP write tools require an elevated scope *and* pass
  through the AI confirmation gate, so a model-requested reboot/factory-reset is surfaced for human
  approval exactly like an in-app AI action. This is a strong, honest safety story — the MCP server
  doesn't get a side door around the gate.
- Ship it as a first-class piece (`backend/devicekit/mcp/`) that Claude Code / Claude Desktop can
  register with a scoped key, plus a `.mcp.json` snippet in the docs.

## Part 4 — Generated client + thin CLI

- Generate a client from the OpenAPI spec; wrap the highest-value verbs in a `devicekit` CLI
  (`devicekit devices ls`, `devicekit automation run <id>`, token auth via `dk_` key + shell
  completions). Small, but it makes the API real for humans too.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | `/api/v1` mount + dual auth (session or `dk_` key) + `require_scope` (pass-through for session) + device scope catalog | one endpoint serves UI + machines |
| 2 | Auto-OpenAPI generator over the blueprint `url_map` + `/api/v1/openapi.json` + docs page | spec stays in sync, no hand-maintenance |
| 3 | MCP server (stdio + HTTP) over the scoped API: curated tools, per-tool scope gating, plan-13 gate on writes | Claude can drive the fleet, safely |
| 4 | Generated client + `devicekit` CLI (token auth, completions) | external + human consumers |

Phase 1 needs plan 20's keys. Phases 2→3→4 are sequential-ish (3 curates over the surface 1
exposes; 4 rides 2's spec).

## Decisions to make while executing (log, don't stop)

- **MCP transport:** stdio (local Claude Desktop) first; add streamable-HTTP for remote once auth
  is proven. Don't block phase 3 on both.
- **Write-tool policy in MCP:** always-gated (recommended) vs scope-only for `autonomous`-mode
  fleets. Lean always-gated; make autonomous an explicit per-key opt-in that's logged.
- **Spec source:** pure `url_map` walk (ServerKit's way) vs a schema library. Prefer the walk —
  it's zero-maintenance and matches the existing envelope shapes.

## Out of scope

- **A public multi-tenant hosted API gateway** (rate-plan tiers, billing). Per-key rate limits can
  ride the existing limiter; monetization is not this plan.
- **Exposing every internal route as MCP tools.** The tool set is deliberately curated + gated;
  raw route parity is a footgun.
- **Rebuilding auth.** Keys + identity are plan 20; this plan *consumes* them.

## ServerKit source map (for implementers)

- OpenAPI generator: `backend/app/services/openapi_service.py`
- Scope middleware: `backend/app/middleware/api_scope_middleware.py` (`require_scope`, catalog)
- Keys (shared with plan 20): `backend/app/services/api_key_service.py`
- Webhook-trigger sibling (lives in plan 22): `backend/app/api/workflows.py` (`/hooks/<id>`)
- **MCP:** no ServerKit prior art — `docs/MCP_SERVER_ACCESS.md` is unrelated. Build against the
  official MCP Python SDK over DeviceKit's own scoped API.
