# Plan 02 — API Blueprint Refactor

**Status:** proposed
**Inspired by:** ServerKit's app-factory + Blueprint layout (`backend/app/__init__.py`, ~90 blueprints under `backend/app/api/`)
**Depends on:** nothing (01 can land before or after; 03 requires this)

## Problem

`backend/devicekit/mixins/api_app.py` is ~2,100 lines (2,078 at last count): every
route for every feature is a nested function inside `api_app()`. Consequences:

- No feature can be registered or unregistered independently — which blocks the
  extension platform (plan 03), whose whole premise is mounting/unmounting route groups.
- Merge conflicts concentrate in one file; navigation is by comment headers.
- Route handlers close over `api_app()` locals (e.g. `_agent_device_states`), which is
  why that state can't be persisted or shared cleanly.

## What ServerKit does

- `create_app()` app factory; each feature is a Flask **Blueprint** module under
  `backend/app/api/` (`plugins.py`, `fleet.py`, `notifications.py`, …), registered in a
  loop with `/api/v1/*` prefixes.
- Blueprints stay thin; logic lives in `backend/app/services/`. In DeviceKit's
  vocabulary, the mixins on `Client` *are* the service layer — that split already
  exists and is good. Only the routing layer needs restructuring.
- Cross-cutting concerns (auth, rate limiting, audit) attach via `before_request` on
  the app or per-blueprint, not per-route.

## Design for DeviceKit

1. New package `backend/devicekit/routes/`, one module per existing section header in
   `api_app.py`:
   `devices.py`, `device_control.py`, `pipeline.py`, `queue.py`, `alerts.py`,
   `activity.py`, `automations.py`, `profiles.py`, `fleet.py`, `fleet_query.py`,
   `agent_devices.py`, `streaming.py`, `visual_regression.py`, `debug_bundles.py`,
   `ai_agent.py`, `events.py` (SSE), `health.py`.
2. Each module exposes `make_blueprint(client) -> Blueprint`. The `client` (the mixin
   composite) is passed in explicitly — handlers call `client.run_automation(...)`
   exactly as they do today. No mixin code changes.
3. `ApiAppMixin.api_app()` shrinks to: create app, configure CORS/limiter/auth
   `before_request`, register all blueprints, return app. The mixin registration order
   convention ("before `ApiAppMixin`") is unchanged.
4. Closure state that currently lives inside `api_app()` (`_agent_device_states`,
   `_sse_clients`, broadcast helper) moves onto the client/mixins where it belongs —
   this is also prep for plans 01 and 07.
5. **URLs do not change.** This is a pure reorganization; `frontend/src/api.js` and the
   Android agent are untouched. Verify with a route-table snapshot before/after
   (`app.url_map` dumped to a file and diffed).

## Migration strategy

Move one section at a time (same order as the file's comment headers), keeping
`api_app.py` importing and registering each extracted blueprint as it goes. Each
extraction is a small, revertable commit. Health + SSE first (smallest), device
control and automations last (largest).

## Risks / notes

- The SSE broadcast helper is used by many mixins — extract it first into its own
  module (`routes/events.py` + a `broadcast()` attached to client) so nothing breaks
  mid-migration.
- Watch for route functions that share helper closures within a section; promote those
  helpers to the owning mixin rather than duplicating.
- Flask blueprint name collisions: keep blueprint names identical to module names.

## Definition of done

`api_app.py` under ~150 lines; every route group is a blueprint module; the dumped
route table (methods + rules) is byte-identical before and after; the app boots and the
frontend works with zero `api.js` changes.
