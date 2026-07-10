# Plan 09 — Frontend Foundations

**Status:** proposed
**Inspired by:** ServerKit's design-system layer (`frontend/src/components/ds/`,
`components/layouts/ResourceListPage.jsx`), modular API client (`services/api/`),
and assorted hooks (`useTabParam`, `useMetrics`, `useConfirm`)
**Depends on:** nothing — pure frontend track, parallel to backend plans

## Problem

DeviceKit's views are self-contained monoliths: `NodeDetail.jsx` is 1,361 lines,
`AutomationEditor.jsx` 989, `Dashboard.jsx` 696. The only shared pieces are
`StreamCanvas` and `useMjpegStream`. `api.js` is a single 411-line object. Each view
hand-rolls its own tables, empty states, loading states, filters, and modal state.
Extension-contributed UI (plan 04) and every future view pay this duplication tax.

ServerKit's frontend is the counter-example: pages are thin because chrome lives in a
small set of shared primitives. Port the *patterns*, not the SCSS — DeviceKit stays
Tailwind + its existing dark-theme palette (`bg-zinc-900`, `border-main`,
emerald/red/blue/amber accents, lucide `w-4 h-4`).

## What to build (in rough priority order)

### 1. The list-page stack

ServerKit's `ResourceListPage` composes: status segment control + search field +
filter drawer + **bulk-actions bar** + `DataTable` + three-state empty handling
(loading / truly-empty / filtered-empty). Its `DataTable` is declarative columns
(`{key, label, render, sortable, sortValue, width}`) with client sort and clickable
rows. Bulk selection is a `Set` of ids passed down.

DeviceKit components: `components/DataTable.jsx`, `components/ListPage.jsx`,
`components/EmptyState.jsx` (supports `loading`/`icon`/`title`/`action`),
`components/BulkActionsBar.jsx`. First adopters: Automations list, Dashboard device
registry, FleetGroups. Bulk actions integrate with the existing
`/fleet/query/bulk-action` endpoint.

### 2. Modular API client

Split `api.js` by domain, mirroring ServerKit's `services/api/` (base `client.js` with
the `request()` helper + `X-API-Key` injection; domain modules `devices.js`,
`automations.js`, `fleet.js`, `streaming.js`, `extensions.js`…; an `index.js`
aggregator preserving the current `api.*` call sites so nothing breaks). This is
mechanical and makes the SDK export (plan 04) clean.

### 3. URL-as-state hooks

`useTabParam()` (tab in the URL → shareable, refresh-proof — `NodeDetail`'s tabs and
the future Settings view want this), plus keeping filters/selection in search params on
list pages. Small hooks, big usability win.

### 4. `useConfirm()`

ServerKit's `ConfirmContext`: `const confirm = useConfirm(); if (await confirm({title,
body, destructive: true})) …` — replaces per-view modal state for deletes (automations,
groups, baselines, bundles). One provider, one dialog component.

### 5. Realtime hook hardening

Port the shape of `useMetrics`: **stream-first with automatic polling fallback**
(subscribe to SSE; if not connected within 3s or it drops, poll; stop polling on
reconnect; expose `{data, connected, refresh}`). DeviceKit's `subscribeToEvents` SSE
client gets wrapped in `useEvents(handlers)` / `useDeviceState(id)` hooks so views stop
wiring `EventSource` by hand.

### 6. Toast normalization

Views currently ad-hoc their feedback. One `ToastProvider` (either `sonner` like
ServerKit, or a ~80-line Tailwind implementation) with `toast.success/error/info`,
used by the API layer for failures.

### 7. Terminal input queue (targeted fix)

ServerKit's `RemoteTerminal` serializes keystrokes through an input queue because each
keystroke is an HTTP POST and parallel POSTs scramble fast typing. `RemoteADB.jsx`'s
terminal has the same transport shape — port the `inputQueue`/`flushInput` pattern.

## Non-goals

- No component library / no Radix adoption — Tailwind primitives only.
- No TypeScript migration, no React Query — keep the stack; improve the structure.
- No wholesale view rewrites: each view adopts primitives opportunistically when
  touched. The stack exists so *new* views (marketplace, notifications, settings,
  jobs) start thin.

## Phases

1. `DataTable` + `EmptyState` + `useConfirm` + toasts (adopt in Automations list).
2. `api.js` split + `ListPage`/bulk-selection (adopt in Dashboard registry).
3. URL-as-state hooks + SSE hooks + terminal input queue.

## Definition of done

A new list view (e.g. the plan 04 marketplace "Installed" tab) is buildable in
< 150 lines by composing the stack; Automations and Dashboard use shared
table/empty/confirm primitives; `api.js` is a directory of domain modules with
unchanged call sites.
