# Plan 26 — Command Palette v2: F1, Omnisearch & Settings Deep-Links

**Status:** 📝 planned
**Inspired by:** ServerKit's current palette stack — `layouts/DashboardLayout.jsx` (three
open bindings), `components/CommandPalette.jsx` (prefix modes, category weights),
`data/settingsIndex.js` + `hooks/useSettingFocus.js` (settings deep-links that *flash* the
card), `utils/paletteFrecency.js` (frecency ranking), and `backend/app/services/search_service.py`
(a real `/search` entity omnisearch).
**Depends on:** 10 (✅ shipped — this plan **extends** it, not a rewrite), 12 (settings shell),
20 (RBAC — gating admin-only results), 16 (docs suite, soft — `?` docs mode)

## Problem

Plan 10 shipped a solid `Ctrl/Cmd+K` palette (cmdk 1.1.1, fuzzy scorer, pages + devices +
automations + actions + extension entries + FQL `>` mode). Since then ServerKit's palette
grew four things DeviceKit's lacks, and the user's number-one ask is the first:

1. **More open bindings** — `F1` and `Ctrl/Cmd+Shift+P` (VS Code muscle memory), not just `Ctrl+K`.
2. **Settings omnisearch** — every settings *card* is indexed; selecting one deep-links to
   `/settings/<tab>?focus=setting:<id>` and the card scrolls into view and flashes.
3. **Frecency** — DeviceKit keeps "last 6 recents"; ServerKit ranks by frequency+recency with
   a 14-day exponential half-life, and blends that score into live ranking.
4. **Backend `/search`** — entities are fetched via one authz-scoped omnisearch endpoint
   instead of client-side fetch-all-on-open (which stops scaling past a few dozen devices).

## How ServerKit does it (the parts worth porting)

- **Bindings** live in one `document` keydown in the layout: `cmdK || cmdShiftP || f1` toggles;
  `e.preventDefault()` on F1 is required (stops browser help).
- **Prefix modes:** bare = everything, `>` = actions only, `?` = docs only; footer advertises
  `↵ open · > actions · ? docs · esc close`. *(DeviceKit already uses `>` for FQL — keep that;
  see Decisions.)*
- **Settings index:** a flat registry `{ id, label, description, keywords, tab, adminOnly }` →
  path `/settings/<tab>?focus=setting:<id>`; a `useSettingFocus()` hook on the settings page
  registers cards by id, scrolls the target into view, and applies a 2 s ring/wash keyframe.
  A lint script (`scripts/check-settings-index.mjs`) fails CI if a settings tab has zero entries.
- **Ranking:** cmdk's filter disabled (`shouldFilter={false}`); hand scorer (substring
  fast-path + prefix/word-boundary bonuses, else ordered subsequence) — DeviceKit already
  ported this in plan 10. New: final score = `fuzzy + CATEGORY_WEIGHT + min(frecency, 10)`,
  fixed `GROUP_ORDER`, `PER_GROUP_CAP = 6`, `OVERALL_CAP = 30`.
- **Backend omnisearch:** `SearchService.search(user, term, workspace)` returns rows
  `{type, label, sublabel, path}` across all entity tables, authz-scoped; frontend debounces
  200 ms, min 2 chars, maps `type → category`.

## Design for DeviceKit

### Part 1 — Bindings + frecency (client-only)

- Add `F1` and `Ctrl/Cmd+Shift+P` alongside `Ctrl/Cmd+K` in `CommandPalette.jsx:141-152`
  (the listener already exists there; keep it there rather than a new hook).
- Replace the `devicekit_palette_recents` last-6 list with `utils/paletteFrecency.js`
  (copy ServerKit's ~40-line util: exponential decay, 14-day half-life, `recordUse` /
  `recentIds(8)` / `frecencyScore`). Key: `devicekit:palette:frecency`.
- Footer hint row: `↵ open · > query fleet · ? docs · esc`.

### Part 2 — Settings index + deep-link flash + authz

- `data/settingsIndex.js`: one entry per settings *card* across the ~14 panes in
  `components/settings/` (General, ApiAccess, Security, Users, ApiKeysPane, Workspaces,
  Vault, AuditLog, AiSettings, Streaming, Bundles, Notifications, Appearance, About).
- `hooks/useSettingFocus.js` + an `.is-setting-focused` keyframe in `index.css`; Settings
  panes spread `register(id)` onto each card container.
- `usePaletteAuthz()`: drop `adminOnly` entries for non-admins (`useAuth().isAdmin`) and
  respect workspace nav visibility — the palette must never surface a page the sidebar hides.
- Optional but cheap: a `scripts/check-settings-index.mjs` lint mirroring ServerKit's.

### Part 3 — Backend `/search` omnisearch

- `SearchMixin` (`backend/devicekit/mixins/search.py`, composed before `ApiAppMixin` per the
  house pattern) + `GET /search?q=` blueprint. Entities: **devices** (name/serial/model),
  **automations**, **profiles**, **fleet groups**, **extensions**, **jobs** (recent),
  **users/workspaces** (admin only). Each row `{type, label, sublabel, path}`; scope by the
  caller's workspace + role (plan 20's `scope_query`).
- Frontend: in `all` mode, ≥2 chars, debounce 200 ms; replaces the fetch-everything-on-open
  device/automation providers. Map `type → category` (Devices, Automations, Profiles, Groups,
  Extensions, Jobs) with lucide icons and category weights (Settings=6, Pages/Actions=4,
  entities=1); entity hits floor at score 0 so a serial fragment always shows.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | F1 + Ctrl/Cmd+Shift+P bindings, frecency ranking replacing recents, footer hints | `F1` from any view opens the palette; most-used items float to the top of the empty screen |
| 2 | Settings card index + `?focus=setting:` deep-link flash + authz gating | typing "retention" → enter lands on `/settings/bundles` with the retention card flashing; non-admins never see Vault/Users entries |
| 3 | `SearchMixin` + `GET /search`, async entity provider with weights/caps | with 200 devices, typing 3 chars of a serial returns in one debounced request instead of pre-fetching every table |

Phases are independent; 1 is a one-sitting win and should land first since it's the direct ask.

## Decisions to make while executing (log, don't stop)

- **`>` prefix collision:** DeviceKit's `>` is FQL (plan 10's differentiator); ServerKit's is
  actions-only. **Keep `>` = FQL**, leave actions in the bare mode, add `?` = docs. Log it.
- **Docs mode targets:** plan 16's docs suite if routable in-app, else external repo links.
  Hide the category if neither exists yet.
- **`/search` vs `/api/v1`:** ship as an internal panel route first; mirroring into the public
  API (plan 21) is follow-up.

## Definition of done

From any view, **F1** (or `Ctrl+K`, or `Ctrl+Shift+P`) opens the palette; typing part of a
device serial hits `/search` and enter lands on `/node/<id>`; typing part of a settings card
name lands on the right tab with the card flashing; items you use daily rank above things you
touched once; `> battery < 20` still runs FQL exactly as plan 10 shipped it.

## Out of scope

- **Cross-device frecency sync.** localStorage-only, like ServerKit.
- **Palette theming.** Visual refresh rides plans 27/28.

## ServerKit source map (for implementers)

- Bindings: `frontend/src/layouts/DashboardLayout.jsx`
- Orchestrator + weights/caps/modes: `frontend/src/components/CommandPalette.jsx`
- Registries: `frontend/src/data/palettePages.js`, `data/commandActions.js`, `data/settingsIndex.js`
- Utils/hooks: `utils/paletteScore.js`, `utils/paletteFrecency.js`, `hooks/usePaletteAuthz.js`, `hooks/useSettingFocus.js`
- Backend: `backend/app/api/search.py`, `backend/app/services/search_service.py`
- Styling: `styles/components/_command-palette.scss`, `styles/components/_ui.scss` (~728–856)
