# Plan 04 — Extension Platform: Frontend

**Status:** proposed
**Inspired by:** ServerKit's `frontend/src/plugins/` (contributions.js, ExtensionRoutes.jsx,
PluginSlot.jsx, sdk/), `pages/Marketplace.jsx`, and ADR 0001 (frontend delivery decision)
**Depends on:** 03 (contribution envelope is served by the backend)

## Concept

Extensions declare UI **declaratively** in their manifest (`contributions` block); the
backend merges all active extensions' contributions into one envelope at
`GET /extensions/contributions`; the React app fetches it and renders contributed nav
items, routes, widgets, and command-palette entries dynamically. Extension pages import
shared components from a stable `devicekit-sdk` alias.

## The delivery decision (make it consciously)

ServerKit weighed three options for shipping extension frontend code (ADR 0001):

- **(a) Runtime ESM bundles** — sha256-verified, imported via Blob URL with an
  importmap resolving `react`/`react-router-dom`/sdk to the host's singletons. Powerful
  but risks React version skew; ServerKit built it (`plugins/runtime/loader.js`) and
  left it **dormant**.
- **(b) Iframes** — isolation but no shared theme/nav; escape hatch only.
- **(c) Pre-bundled builtins + backend-only third-party** — builtin extension frontends
  live in-repo and compile into the app bundle; third-party extensions contribute
  backend + step types only. **ServerKit shipped (c).**

**Recommendation: adopt (c) for DeviceKit too — and it costs less here.** DeviceKit's
best extension surface (automation step types, plan 03) already needs **zero frontend
code** because the editor auto-renders step config forms from the API. A third-party
extension with no custom pages is still fully useful. Custom pages are a
builtin/first-party privilege until runtime loading is justified.

## Contribution envelope → rendering

Port ServerKit's model (`contributions.js` + `ExtensionRoutes.jsx`):

| Kind | Shape | Renders in |
|------|-------|-----------|
| `nav` | `{id, label, route, section, icon}` | `App.jsx` sidebar — merge into `navSections` (Management/Engineering/AI + new "Extensions" section), core wins on id collision |
| `routes` | `{path, component}` | `<Routes>` in `App.jsx`, each wrapped in a per-extension error boundary |
| `widgets` | `{slot, component}` | `<ExtensionSlot name="..."/>` mount points |
| `command_palette` | `{label, path, keywords}` | plan 10 palette |
| `page_titles` | `{"/path": "Title"}` | `document.title` updater |

Implementation pieces:

1. `frontend/src/extensions/contributions.js` — singleton fetch + cache + pub/sub
   `useContributions()` hook; `refreshContributions()` called after install/enable/
   disable. Build-time fallback via `import.meta.glob('../extensions/*/index.jsx',
   { eager: true })` so builtins render even if the endpoint is briefly unavailable.
2. `resolveComponent(slug, name)` maps the manifest's component string to the
   extension module's named export.
3. `frontend/src/extensions/ExtensionSlot.jsx` — named mount points. Seed with:
   `dashboard.top`, `node-detail.tabs`, `run-detail.panels`, `settings.panels`
   (plan 12). Every active extension widget matching the slot renders there.
4. **Error containment:** per-extension React error boundary; unresolvable
   components are skipped with a dev warning — a broken extension must never
   white-screen the app (ServerKit's "fail soft, loudly").
5. **Icon safety:** manifest icons are inline SVG strings — port
   `sanitizeSvgInner()` (`src/utils/sanitizeSvg.js`) before `dangerouslySetInnerHTML`.

## Builtin frontend source-of-truth

Follow ServerKit decision D5: `builtin-extensions/<slug>/frontend/` is the source of
truth; `frontend/src/extensions/<slug>/` is a generated artifact synced by a script
(`scripts/sync-builtin-frontends.mjs` port) with a `--check` drift gate in CI.

## The frontend SDK (`devicekit-sdk`)

Vite alias → `frontend/src/extensions/sdk/index.js`, exporting a **versioned** stable
surface: `api` (the `api.js` client), `subscribeToEvents`, `StreamCanvas`,
`useMjpegStream`, shared UI primitives as they emerge from plan 09, and router helpers.
`SDK_VERSION` mirrored in a backend constant and asserted by a test. Internal
restructures never break extensions — only the SDK surface is contract.

## Marketplace UI

New `Extensions.jsx` view (route `/extensions`, sidebar under Management), modeled on
`pages/Marketplace.jsx` but Tailwind-styled to DeviceKit's dark theme
(`bg-zinc-900`/`border-main`, lucide icons):

- **Browse tab:** card grid merging builtin + registry catalogs. Cover-art fallback
  chain (registry logo → manifest SVG → category glyph). Category + permission filters.
- **Detail modal:** description, screenshots, **requested-permissions consent chips**
  (from the plan 03 preview endpoint), version/compat gate, install button.
- **Installed tab:** rows with enable/disable toggle, update-available badge
  (registry version > installed), configure (schema-driven form from
  `config_schema`: booleans/enums/numbers/secrets), uninstall dialog with
  **keep-data vs purge** choice.

## Phases

1. Contributions endpoint consumption: nav + routes + error boundaries + titles
   (builtins only, build-time glob).
2. `ExtensionSlot` + first slots in Dashboard and AutomationRunDetail.
3. Marketplace view: installed management, then registry browse + consent install flow.
4. SDK alias + sync script + CI drift gate.

## Definition of done

A builtin extension contributes a sidebar item, a routed page, and a dashboard widget
with no edits to `App.jsx` beyond the generic contribution rendering; disabling it in
the marketplace removes its nav/routes/widgets immediately; a deliberately-throwing
extension component shows a contained failure card while the rest of the app works.
