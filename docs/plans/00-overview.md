# DeviceKit Improvement Plans — Overview

Ideas harvested from **ServerKit** (a sibling project by the same author) and its
companion repos (`serverkit-extensions`, `builtin-extensions/`) adapted to DeviceKit's
architecture. ServerKit is also Flask + React, so most backend patterns port nearly 1:1.

## The plans

| # | Plan | What it borrows | Depends on |
|---|------|-----------------|------------|
| 01 | [Persistence layer](01-persistence-layer.md) | SQLAlchemy models as source of truth | — |
| 02 | [API blueprint refactor](02-api-blueprint-refactor.md) | App-factory + Blueprint layout | — |
| 03 | [Extension platform — backend](03-extension-platform-backend.md) | plugin.json manifest, install pipeline, SDK, status guard, registry repo | 01, 02 |
| 04 | [Extension platform — frontend](04-extension-platform-frontend.md) | Contribution envelope, plugin slots, marketplace UI | 03 |
| 05 | [Jobs, queue bus & scheduler](05-jobs-and-queue.md) | SQL-backed queue, unified job consumer, DB-defined schedules | 01 |
| 06 | [Notification bus](06-notification-bus.md) | Event catalog, per-channel delivery, notification center | 01, 05 |
| 07 | [Agent security & fleet registry](07-agent-security-and-fleet-registry.md) | HMAC auth, heartbeat reaper, capability targeting, pairing | 01 |
| 08 | [Metrics history & fleet monitoring](08-metrics-history.md) | Rollup pipeline (min→hour→day), retention tiers, fleet charts | 01, 05 |
| 09 | [Frontend foundations](09-frontend-foundations.md) | ResourceListPage/DataTable stack, modular API client, URL-as-state | — |
| 10 | [Command palette](10-command-palette.md) | cmdk palette with devices + FQL + extension entries | 09 (soft) |
| 11 | [Dashboard widget system](11-dashboard-widgets.md) | Reorderable/toggleable widgets, renderer map, plugin slots | 09 (soft) |
| 12 | [Settings view & theming](12-settings-and-theming.md) | URL-driven tabs, accent theming, extension settings panels | — |
| 13 | [AI confirmation gate](13-ai-confirmation-gate.md) | Human-in-the-loop approval for write tools, tool registry filtering | — |
| 14 | [Python package publishing](14-devicekit-python-package.md) | ✅ Resolved — published as [`droidlink`](https://pypi.org/project/droidlink/) from its own repo (bare `devicekit` is blocked by PyPI's similarity rule) | — |
| 15 | [Extension pack one](15-extension-pack-one.md) | ServerKit's "validate the platform with real builtin plugins" — browser (CDP), file explorer (builtin frontend), notification capture (jobs + bus) | 03, 04, 13 |
| 16 | [Documentation suite](16-documentation-suite.md) | ServerKit's docs *system* — architecture doc, fleet contract, SDK/manifest reference, ADRs, optional docs site | soft: 15 (worked examples) |
| 17 | [Extension dependencies + SERP](17-extension-dependencies-and-serp.md) | `requires_extensions` + `sdk.extension()` seam so plugins compose; `devicekit-serp` searches via `devicekit-browser` | 15 |
| 18 | [App-driver extensions](18-app-driver-extensions.md) | `device_requirements` (pin + provision a 3rd-party APK) + version-keyed adapters for UI drift + device version policy; `devicekit-vpn` example | 15, 13 |
| 19 | [AI consolidation + Prompture Hub](19-ai-consolidation-and-prompture-hub.md) | Retire the direct OpenAI path (all AI via Prompture); optional `prompture-hub` backend with detection/health/setup + per-extension scoped LLM keys | 16-era Prompture, 12, 03 |

### Second wave (20–25) — harvested in a deeper ServerKit pass

Plans 01–19 ported ServerKit's *platform foundations*. A second, closer read of ServerKit
(`C:\Users\Juan\Documents\GitHub\ServerKit`) surfaced a further wave of mature, mostly-shipped
patterns worth porting. Each of these plans carries its own **"ServerKit source map"** section
pointing at the exact source files. Two candidates ServerKit itself hasn't built (MCP server, OTA
agent updates, real on-device sandboxing, multi-node control plane) are called out as *greenfield*
in their plans — places DeviceKit would lead rather than follow.

| # | Plan | What it borrows | Depends on |
|---|------|-----------------|------------|
| 20 | [Identity, RBAC & secrets](20-identity-rbac-and-secrets.md) | Opt-in narrow-only `scope_query` retrofit, users + role matrix, workspaces + membership, hashed scoped API keys, user-attributed audit, Fernet secrets vault | 01, 02 |
| 21 | [Public API + MCP server](21-public-api-and-mcp-server.md) | `/api/v1` + dual auth + `require_scope` pass-through, auto-generated OpenAPI; **MCP server** (greenfield) so Claude can drive the fleet | 20, 02, 13 |
| 22 | [Automation engine v2](22-automation-engine-v2.md) | DAG (nodes+edges, Kahn walk), `logic_if` branch-gate, per-node critical/retry, `${}` interpolation, four trigger types (manual/webhook/cron/event) | 05, 15, 06 |
| 23 | [Desired-state fleet policy](23-desired-state-fleet-policy.md) | `devicekit.yaml` → spec/persist(hash)/plan(+blockers)/apply(idempotent, snapshots)/drift/reconcile/scaffold — MDM-grade policy | 18, 05, 20, 24 |
| 24 | [Fleet health & remediation](24-fleet-health-and-remediation.md) | `fleet_sweep` bounded fan-out + doctor/repair allowlist + drift + z-score anomaly + regression forecast (finishes Phase 22); reframes "scale" as discipline not multi-node | 05, 07, 08, 06 |
| 25 | [Agent lifecycle & backup/DR](25-agent-lifecycle-and-backup.md) | Agent-enforced read-only primitive allowlist, capability negotiation, **OTA agent updates** (greenfield), onboarding state machine, agent-plugin contract, backup + **restore drills** | 07, 05, 08 |

### Third wave (26–28) — palette parity & visual identity

Plans 10 and 12 shipped the first-generation command palette and theming; ServerKit's have
since grown past them, and DeviceKit never had a real logo. These close both gaps.

| # | Plan | What it borrows | Depends on |
|---|------|-----------------|------------|
| 26 | [Command palette v2](26-command-palette-v2.md) | `F1`/`Ctrl+Shift+P` bindings, settings-card index + deep-link flash, frecency ranking, backend `/search` omnisearch (extends 10) | 10, 12, 20 |
| 27 | [Brand identity: purple phone logo](27-brand-identity-purple-phone.md) | Master-SVG pipeline (squircle + indigo gradient), accent-tinted JSX logo, favicon redraw, Android adaptive-icon alignment, purple default accent | 12, 25 (soft) |
| 28 | [Appearance v2: themes & tokens](28-appearance-v2-themes-and-tokens.md) | One CSS-token sheet, dark/light/system via `data-theme` + `matchMedia`, 8-preset + custom accent picker, white-label (extends 12) | 12, 27 |

## Executing a plan

- A local **plan-executor prompt** (`docs/plans/prompt.md`, git-ignored because it
  embeds machine-specific paths and device details) drives any plan: set the plan
  path at the top, paste the whole file into a fresh Claude session, and it
  implements every phase with subagents, verifying and committing as it goes — a
  convention ported from ServerKit.
- The root **[ROADMAP.md](../../ROADMAP.md)** maps these plans onto Phases 23–45
  (plan 08 is the design doc for the existing Phase 22; plans 20–25 map to Phases
  40–45), so the `implement-phase` skill can drive them too.
- The numbered plan docs are tracked in git — commit status updates to them as work
  ships so they stay the source of truth for progress. Only the executor prompt
  stays local.

## Suggested implementation order

```
Foundations:   01 persistence ──► 02 blueprints
                     │                  │
Platform:            ├──► 05 jobs/queue ├──► 03 extension backend ──► 04 extension frontend
                     │         │
Features:            ├──► 06 notifications
                     ├──► 07 agent security
                     └──► 08 metrics history
Frontend:      09 foundations ──► 10 palette, 11 widgets, 12 settings   (parallel track)
AI:            13 confirmation gate                                      (independent)
Packaging:     14 python package ✅ done — droidlink 0.1.0 on PyPI       (independent)
Extensions:    03/04 ──► 15 extension pack one (browser, explorer, notification capture)
                            ├──► 17 ext dependencies + serp (compose plugins)
                            └──► 18 app-driver extensions (provision + version drift)
Docs:          15 ──► 16 documentation suite (architecture, fleet contract, SDK ref, ADRs)
AI:            16-era prompture ──► 19 consolidate on prompture + optional prompture-hub backend

Second wave (ServerKit deep pass):
Identity:      20 identity/RBAC/keys/audit/vault  ──► unlocks 21, scoped keys, multi-tenant hub
API/AI:        20 ──► 21 public /api/v1 + OpenAPI + MCP server (Claude drives the fleet)
Automation:    05 jobs ──► 22 automation engine v2 (DAG + triggers)
Policy:        18 app-driver + 20 vault + 24 drift ──► 23 desired-state fleet policy (devicekit.yaml)
Fleet ops:     05 + 08 ──► 24 fleet health, sweeps & allowlisted remediation (finishes Phase 22)
Agent:         07/29 + 05 ──► 25 agent lifecycle, OTA & backup/DR
```

Recommended order for the second wave: **20 first** (identity is the substrate 21's scoped keys,
25's tokens, and 19's per-extension hub keys all assume), then 21 and 24 in parallel, then 22 → 23
(policy applies automations), with 25 landable independently.

Plans 09–13 have no hard backend dependencies and can proceed in parallel with the
foundation work (14 is already done). The extension platform (03/04) is the centerpiece but deliberately
sits *after* persistence and the blueprint refactor — installed-extension state must
survive restarts, and extension routes need a blueprint-shaped app to mount into.

## Why these foundations first

DeviceKit today keeps **all state in-memory** (class-level lists in mixins; the
DynamoDB/S3 mixins exist but nothing calls them) and serves every route from a single
~2,100-line `api_app.py`. ServerKit's most transferable lesson is structural: SQLAlchemy
rows as the source of truth, blueprints per feature, and services that background
workers and plugins share. Nearly every borrowed concept (installed extensions, job
rows, notification deliveries, metrics rollups) presumes a database.

## ServerKit source map (for implementers)

- Extension platform: `backend/app/services/plugin_service.py`, `backend/app/plugins_sdk/`, `docs/EXTENSIONS.md`, `docs/adr/0001-*.md`, `docs/adr/0002-*.md`
- Registry repo: [`serverkit-extensions`](https://github.com/jhd3197/serverkit-extensions) (index.json + schema + validators + CI)
- Jobs/queue: `backend/app/queue_bus/`, `backend/app/jobs/`
- Notifications: `backend/app/notifications/`
- Agent fleet: `backend/app/agent_gateway.py`, `backend/app/services/agent_registry.py`, `docs/FLEET_CONTRACT.md`
- Metrics history: `backend/app/services/metrics_history_service.py`
- Frontend patterns: `frontend/src/plugins/`, `frontend/src/components/ds/`, `frontend/src/hooks/useMetrics.js`, `frontend/src/components/CommandPalette.jsx`
- Plan-executor prompt convention: `ServerKit/docs/plans/prompt.md`

Second-wave source map (plans 20–25):

- Identity/RBAC/keys/audit/vault (20): `services/workspace_service.py` + `docs/WORKSPACE_SCOPING.md`, `services/permission_service.py`, `models/api_key.py` + `services/api_key_service.py`, `services/audit_service.py`, `services/secret_vault_service.py`
- Public API + OpenAPI (21): `services/openapi_service.py`, `middleware/api_scope_middleware.py` (MCP server is greenfield — no ServerKit prior art)
- Automation engine v2 (22): `services/workflow_engine.py`, `services/workflow_service.py`, `models/workflow.py`, `api/workflows.py` (`/hooks/<id>` + `enqueue_execution`)
- Desired-state policy (23): `services/manifest_spec_service.py`, `manifest_persistence_service.py`, `manifest_apply_service.py`, `manifest_sync_service.py`, `manifest_scaffold_service.py`, `docs/SERVERKIT_YAML.md`
- Fleet health & remediation (24): `services/fleet_sweep.py` + `docs/FLEET_CONTRACT.md`, `doctor_service.py`, `fleet_doctor_service.py`, `fleet_repair_service.py`, `drift_service.py`, `fleet_monitor_service.py`, `backup_alert_service.py`
- Agent lifecycle & backup (25): `docs/AGENT_SURVEY_SPEC.md`, `models/agent_plugin.py` (schema only — runtime is a stub), `services/server_onboarding_service.py`, `backup_drill_service.py` + `backup_verify_service.py` + `docs/BACKUP_PROTECTION.md`
