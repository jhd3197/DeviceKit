# Plan 11 — Dashboard Widget System

**Status:** proposed
**Inspired by:** ServerKit's `frontend/src/pages/Dashboard.jsx` +
`hooks/useDashboardLayout.js` (renderer map, localStorage layout, plugin slots)
**Depends on:** 09 (soft), 04 (extension widgets, optional)

## Concept

Turn `Dashboard.jsx` (696 lines, fixed layout) into a composition of self-contained
widgets the user can toggle, reorder, and (via extensions) add to. Different DeviceKit
users have genuinely different dashboards: a CI-lab operator cares about device locks
and pipeline status; a QA lead cares about run failures and regressions; a device-farm
admin cares about battery/storage fleet health.

## How ServerKit does it (deliberately simple — worth copying as-is)

- **Not** a free-form drag-grid. Widgets are an ordered list with visibility flags:
  `toggleWidget(id)`, `moveWidget(id, dir)` (up/down), `resetLayout()`.
- Layout persists in `localStorage`, **merged forward-compatibly with
  `DEFAULT_WIDGETS`** — new widgets ship visible-by-default and appear on upgrade
  without nuking the saved order.
- Rendering is a `WIDGET_RENDERERS` map keyed by widget id; the page maps over the
  visible list. Each widget owns its data fetching and refresh interval (per-widget
  refresh selector).
- `<PluginSlot name="dashboard.top"/>` lets extensions inject widgets.

## Design for DeviceKit

1. `hooks/useDashboardLayout.js` — port nearly verbatim (order + visibility +
   localStorage + forward-merge).
2. Carve the existing dashboard into initial widgets, each a component in
   `components/widgets/`:
   - `FleetSummary` — counts by status (online/offline/locked), tap-through filters
   - `DeviceRegistry` — the device grid/table (the big one; uses the plan 09 stack)
   - `FQLBar` — saved queries + query input (already exists inline)
   - `ActiveRuns` — currently executing automations with live step progress (SSE)
   - `RecentFailures` — last N failed runs, deep-link to run detail + debug bundle
   - `PipelineStatus` — latest builds/tests
   - `Alerts` / `Notifications` — recent events (plan 06)
   - `FleetHealth` — battery/storage sparklines (plan 08)
3. An "edit layout" mode: gear icon → each widget gets show/hide + up/down controls
   (ServerKit's exact interaction; no drag-drop dependency).
4. `<ExtensionSlot name="dashboard.top"/>` + extension `widgets` contributions render
   alongside (plan 04).
5. Per-widget refresh: widgets relying on SSE need none; polling widgets expose an
   interval selector like ServerKit's.

## Why not react-grid-layout / drag-drop?

ServerKit shipped ordered-list-with-toggles and it's the right call: zero dependency,
keyboard accessible, mobile-sane, and forward-compatible merging is trivial. A 2-D
grid can come later if anyone actually asks.

## Phases

1. Extract widgets from `Dashboard.jsx` (pure refactor, fixed layout).
2. `useDashboardLayout` + edit mode + persistence.
3. New widgets (ActiveRuns, RecentFailures) + extension slot.

## Definition of done

`Dashboard.jsx` is a thin composer (< 150 lines); hiding/reordering widgets survives
reload; a new widget added to `DEFAULT_WIDGETS` appears for users with saved layouts;
an extension widget renders in the slot without dashboard edits.
