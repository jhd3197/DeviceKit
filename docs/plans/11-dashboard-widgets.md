# Plan 11 — Dashboard Widget System

**Status:** ✅ shipped (all 3 phases)
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

1. ✅ Extract widgets from `Dashboard.jsx` (pure refactor, fixed layout).
   Carved into `components/widgets/{FleetSummary,FleetHealth,FQLBar,DeviceRegistry}`
   + `hooks/useFleetData.js` (shared fleet feed) + `components/ds/MetricCard.jsx`.
   The FQL bar owns query state and reports its result set up so the registry can
   show matches (the one cross-widget link). Behavior/layout unchanged.
2. ✅ `useDashboardLayout` + edit mode + persistence. Ported from ServerKit
   (`hooks/useDashboardLayout.js`, `localStorage` key `devicekit_dashboard_layout`,
   forward-merge against `DEFAULT_WIDGETS`). Gear button → `DashboardLayoutEditor`
   popover with per-widget show/hide + up/down + reset. Dashboard maps a
   `WIDGET_RENDERERS` map over the visible list.
3. ✅ New widgets `ActiveRuns` (running/queued automations with live step-progress,
   per-widget refresh selector, polls `/automations/runs`) and `RecentFailures`
   (last N failed runs, deep-link to run detail). Both appended to
   `DEFAULT_WIDGETS` so the phase-2 forward-merge surfaces them for saved layouts.
   The `dashboard.top` `ExtensionSlot` (plan 04) already renders extension widgets
   alongside.

Deviation: the plan lists `PipelineStatus` / `Alerts` / `FleetHealth` as candidate
widgets; `FleetHealth` shipped, and `ActiveRuns`+`RecentFailures` were the phase-3
headline. `PipelineStatus`/`Alerts`/`Notifications` widgets are left as easy
follow-ons (add a renderer + a `DEFAULT_WIDGETS` entry — forward-merge does the rest).
No `ROADMAP.md` exists in the repo, so there were no roadmap checkboxes to tick.

## Definition of done

`Dashboard.jsx` is a thin composer (< 150 lines); hiding/reordering widgets survives
reload; a new widget added to `DEFAULT_WIDGETS` appears for users with saved layouts;
an extension widget renders in the slot without dashboard edits.
