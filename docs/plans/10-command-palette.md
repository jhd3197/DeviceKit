# Plan 10 — Command Palette

**Status:** 🚧 in progress (phases 1–2 ✅)
**Inspired by:** ServerKit's `frontend/src/components/CommandPalette.jsx` (cmdk,
`Cmd/Ctrl+K`, static pages + live entities + extension entries + fuzzy scoring)
**Depends on:** 09 (soft — shares hooks/styling), 04 (extension entries, optional)

## Concept

`Cmd/Ctrl+K` anywhere opens a palette that jumps to pages, **devices**, automations,
and actions. For a fleet tool this is disproportionately valuable: with 30 devices,
"type three letters of the serial and hit enter" beats any amount of dashboard
scanning. DeviceKit also has an asset ServerKit doesn't: **FQL** — the palette can
double as a query launcher.

## How ServerKit does it

- `cmdk` library; binding lives in the layout component (ignores keystrokes while
  an input is focused).
- Sources merged at open time: static page list, **extension-contributed entries**
  (from the contributions envelope: `{label, path, category, keywords}`), and
  **dynamically fetched entities** (containers, servers) fetched on open — not kept
  hot.
- A small fuzzy scorer ranks across categories; results grouped by category
  (Pages / Servers / Actions).

## Design for DeviceKit

1. `components/CommandPalette.jsx` using `cmdk` (works fine with Tailwind), mounted in
   `App.jsx`; `Ctrl/Cmd+K` global listener.
2. Sources:
   - **Pages** — static list mirroring `navSections` (Dashboard, Automations,
     Pipeline, Remote ADB, Fleet Groups, Compare, Profiles…).
   - **Devices** — fetch on open from the existing `/devices` (name, serial, model,
     status dot); enter → `/node/<id>`.
   - **Automations** — fetch on open; enter → editor; a secondary "Run" action.
   - **Actions** — "New automation," "Compare devices," "Install extension"…
   - **Extensions** (plan 04) — `command_palette` contributions merge in.
   - **FQL mode** — input starting with `>` (or a "Query fleet…" row) sends the rest
     to `/fleet/query` and shows matching devices inline; enter jumps to the device,
     or "open in Dashboard" applies the query to the registry view. This reuses the
     existing validate/query endpoints untouched.
3. Fuzzy scoring: port ServerKit's small scorer (substring + word-boundary bonus);
   no dependency needed beyond cmdk.
4. Recent items: keep last N selections in `localStorage`, shown when the query is
   empty.

## Phases

1. ✅ Palette + pages + devices + automations (`components/CommandPalette.jsx`, cmdk 1.1.1,
   `Ctrl/Cmd+K`, ported fuzzy scorer, sources fetched on open). Mounted in `App.jsx`.
2. ✅ Actions + recents + extension entries. Static actions (New Automation, Compare
   Devices, New Profile, Install Extension); `localStorage` recents (last 6) shown on an
   empty query; `command_palette` contributions merge in as their own category groups.
3. 🚧 FQL mode.

## Definition of done

From any view, `Ctrl+K` → typing part of a device serial or automation name → enter
lands on the right page; `> battery < 20` lists matching devices inline.
