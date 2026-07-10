# Plan 12 — Settings View & Theming

**Status:** proposed
**Inspired by:** ServerKit's `pages/Settings.jsx` (URL-driven tabs, grouped nav,
extension settings slot) and `contexts/ThemeContext.jsx` (accent ramp derivation,
white-label)
**Depends on:** nothing hard; 04 adds the extension panels slot; 06 adds notification prefs

## Problem

DeviceKit's sidebar links to `/settings` (`App.jsx:45`, currently labeled
"SamanLabs Config") — **and no Settings route or view exists** (dead nav item). Meanwhile settings-shaped state is accumulating with nowhere to live:
API key display, AI provider/model config (Prompture), debug-bundle retention,
streaming defaults, notification channels (plan 06), extension config (plan 03),
theme preference.

## How ServerKit structures it

- `Settings.jsx` is a shell: left nav of ~18 small tab components under
  `components/settings/`, tab selection in the URL (`/settings/:tab` via a
  `useTabParam` hook) so every pane is linkable.
- Tabs grouped into sections ("My Account" vs "Admin") with a segment control.
- `<PluginSlot/>` inside the settings nav — extensions contribute settings panels
  without touching the shell.
- `ThemeContext`: dark/light/system (OS `matchMedia` listener) + a **custom accent
  color that derives a full ramp** (hover/bright/dim/bg/glow) from one hex, written as
  CSS custom properties on `documentElement`; optional white-label (logo/brand name).

## Design for DeviceKit

### Settings shell

1. `views/Settings.jsx` + route `/settings/:tab?` (fixes the dead link), left tab nav,
   panes as small components in `components/settings/`:
   - **General** — instance name, default device timeouts
   - **API Access** — the `X-API-Key` (show/regenerate), future scoped keys
   - **AI** — Prompture provider/model/key config (currently env-only), per-feature
     model overrides (generation vs self-heal vs analysis)
   - **Streaming** — default FPS/quality, recording retention
   - **Debug Bundles** — retention window (endpoint exists), share-token lifetime
   - **Notifications** (plan 06) — channels + per-event preferences
   - **Appearance** — theme + accent (below)
   - **About** — version, agent APK version/download, registry URL
2. `<ExtensionSlot name="settings.panels"/>` so extensions with `config_schema`
   surface their forms here too (plan 04 renders schema-driven forms).
3. Backend: a small `settings` table (plan 01) + `GET/PUT /settings` — several panes
   currently have no persistence to talk to; add it per-pane as they're built.

### Theming (cheap, high-delight)

DeviceKit is Tailwind with a hard-coded emerald accent. Port the accent-ramp idea:

1. Define accent CSS variables in `index.css` (`--accent`, `--accent-hover`,
   `--accent-dim`, `--accent-bg`) and map Tailwind's accent utilities to them
   (Tailwind `colors: { accent: 'rgb(var(--accent) / <alpha-value>)' }`).
2. A ~40-line ramp-derivation function (HSL shift from one hex) + an accent picker in
   Appearance; persist in `localStorage` + settings row.
3. Light mode is optional/later — the ramp mechanism is the part worth having (also
   used by white-labeling if DeviceKit ever needs it).

## Phases

1. Settings shell + route + General/API/About panes (kills the dead link).
2. AI + Streaming + Bundles panes with backend settings persistence.
3. Appearance (accent ramp) + extension panels slot.

## Definition of done

`/settings` renders; every pane is URL-addressable; AI provider config no longer
requires editing `.env`; changing the accent recolors the app instantly and survives
reload.
