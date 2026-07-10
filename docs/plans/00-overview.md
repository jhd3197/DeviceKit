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
| 14 | [devicekit Python package](14-devicekit-python-package.md) | Publish droidlink as `pip install devicekit` — one brand, one repo | — |

## Executing a plan

- A local **plan-executor prompt** (`docs/plans/prompt.md`, git-ignored because it
  embeds machine-specific paths and device details) drives any plan: set the plan
  path at the top, paste the whole file into a fresh Claude session, and it
  implements every phase with subagents, verifying and committing as it goes — a
  convention ported from ServerKit.
- The root **[ROADMAP.md](../../ROADMAP.md)** maps these plans onto Phases 23–34
  (plan 08 is the design doc for the existing Phase 22), so the `implement-phase`
  skill can drive them too.
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
Packaging:     14 python package                                         (independent)
```

Plans 09–14 have no hard backend dependencies and can proceed in parallel with the
foundation work. The extension platform (03/04) is the centerpiece but deliberately
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
