# Plan 28 — Appearance v2: Theme Modes, Design Tokens & White-Label

**Status:** 📝 planned
**Inspired by:** ServerKit's theming stack — `styles/_theme-variables.scss` (one token
sheet: `:root` dark defaults, `[data-theme="light"]` overrides, a `prefers-color-scheme`
block for `system`), `contexts/ThemeContext.jsx` (mode = `data-theme` attribute on `<html>`
with a live `matchMedia` listener; accent = JS-injected CSS vars layered on top), and
`components/settings/AppearanceTab.jsx` (Dark/Light/System picker with mini previews,
8 accent presets + native color input).
**Depends on:** 12 (✅ shipped — this **extends** the accent ramp it built), 27 (Logo
component — white-label replaces it; purple default accent)

## Problem

Plan 12 shipped the accent ramp but deliberately deferred everything else:

- **One hard-coded dark theme.** `body` is literally `background:#000000` in `index.css`;
  surfaces/borders are fixed Tailwind colors (`card #0a0a0a`, `card-alt #050505`,
  `border-main #1a1a1a`, `border-alt #2e2e2e`). No token can be overridden, so no light
  mode is *possible* today.
- `appearance.theme` already exists in `SETTINGS_DEFAULTS` (default `"dark"`) — declared
  in plan 12, **read by nothing**.
- No white-label: instance name exists (`general.instance_name`) but the mark and brand
  name are hard-coded.

"Make the appearance more like ServerKit" = finish this: tokens → modes → white-label.

## How ServerKit does it

- **Everything is a CSS custom property**, defined once in `_theme-variables.scss`:
  backgrounds (`--bg-body/-sidebar/-card/-hover/-elevated`), borders
  (`--border-default/-subtle/-active`), text (`--text-primary/-secondary/-tertiary`),
  semantic (`--green #3ddc97`, `--amber #f5b945`, `--red #fb6f6f`, `--cyan #49c7f0`,
  `--violet #b07bf5`, each with a `-bg` wash), radius/shadow/scrollbar tokens.
- **Mode** = `document.documentElement.setAttribute('data-theme', mode)`;
  `[data-theme="light"]` redefines only surfaces/borders/text/shadows (light sheet:
  `--bg-body #f6f7fb`, `--bg-card #ffffff`, `--text-primary #161a23`, …). `system`
  resolves via `matchMedia('(prefers-color-scheme: dark)')` with a live listener; a media
  query duplicates the light overrides for `[data-theme="system"]`.
- **Accent stays JS-injected** (theme-independent); light mode only softens the washes
  (`--accent-bg` 0.13 → 0.10 alpha, `--accent-glow` 0.35 → 0.22).
- Persistence is localStorage (`theme`, `accent_color`, `white_label` JSON) — DeviceKit
  does better here: mirror to the settings row like plan 12 did for accent.

## Design for DeviceKit

### Part 1 — Tokenize (zero visual change)

- Add a token block to `index.css` `:root` alongside the existing accent vars:
  `--bg-body`, `--bg-card`, `--bg-card-alt`, `--bg-hover`, `--border-main`, `--border-alt`,
  `--text-primary`, `--text-secondary`, plus semantic `--ok/--warn/--err/--info` (current
  values: emerald/amber/red/blue). **Dark keeps today's exact pure-black values** —
  DeviceKit's black-on-black identity is a feature, not slate drift.
- Point `tailwind.config.js` colors at the vars using the plan-12 pattern
  (`card: 'rgb(var(--bg-card) / <alpha-value>)'`, R G B triplets). Because the Tailwind
  *class names* don't change (`bg-card`, `border-border-main`, …), the ~40 view files need
  **no edits** for this phase; only raw hex in `index.css` and inline styles get swept.

### Part 2 — Dark / Light / System modes

- `theme.js` grows `setThemeMode(mode)` / `getStoredThemeMode()` / `bootTheme()`
  (localStorage `devicekit_theme` for first paint, called next to `bootAccent()` in
  `index.jsx`), sets `data-theme` on `<html>`, `matchMedia` listener for `system`.
- `[data-theme="light"]` block in `index.css` overriding the Part-1 tokens — port
  ServerKit's light sheet, adapted to DeviceKit's neutral gray-blues; soften accent washes.
- Persist to the existing `appearance.theme` settings key (finally read it); server value
  reconciles over localStorage on load, exactly like plan 12's accent flow.
- Appearance pane: Dark/Light/System segmented picker with ServerKit-style mini preview
  swatches, above the existing accent section.
- **Sweep pass:** grep views for hard-coded `#000`/`#0a0a0a`/`text-white`-as-primary and
  the tramo `--tr-*` mapping; anything that ignores tokens will glow wrong in light mode.
  Log stragglers rather than chasing all 68 KB of NodeDetail in one phase.

### Part 3 — Appearance pane v2 + white-label

- Accent presets → ServerKit's 8 (Indigo `#6366f1`, Ocean `#0ea5e9`, Forest `#10b981`,
  Sunset `#f97316`, Rose `#f43f5e`, Violet `#8b5cf6`, Amber `#f59e0b`, Cyan `#06b6d4`) +
  Periwinkle `#6d7cff` default (plan 27) + native `<input type="color">` (plan 12 shipped
  a hex text input; keep both).
- White-label: `appearance.brand_name` + `appearance.logo` (data-URI, size-capped)
  in `SETTINGS_DEFAULTS`; `Logo.jsx` (plan 27) renders the override `<img>` when set;
  PageTitle and login use `brand_name`. Admin-only card in Appearance.
- Palette action "Toggle theme" (plan 26's `commandActions` ctx gets `toggleTheme`).

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | Surface/border/text/semantic tokens + Tailwind var mapping, dark values unchanged | pixel-identical dark UI (screenshot diff a few views); every color now has one source of truth |
| 2 | Light + System modes, `bootTheme()`, `appearance.theme` wired, mode picker | switching to Light recolors instantly with no reload and survives restart in another browser; System follows an OS toggle live |
| 3 | 8+1 presets + color input, white-label brand name/logo, palette toggle-theme action | an admin renames the instance and uploads a mark; login + sidebar + tab title follow; reset returns to the purple phone |

Phase 1 must land alone and be verified pixel-identical before 2 starts.

## Decisions to make while executing (log, don't stop)

- **Light palette values:** ServerKit's `#f6f7fb`-family verbatim vs a warmer neutral.
  Recommend verbatim to start — it's proven; tune later.
- **Semantic tokens in light mode:** keep identical hexes (they're on washes, usually fine)
  vs darken slightly for contrast. Check the four status colors against white cards, adjust
  only failures.
- **tramo editor** (`--tr-*` vars): map to the new tokens if trivial; otherwise pin the
  editor dark and log it — an embedded dark canvas in a light app is acceptable v1.

## Definition of done

Appearance shows theme mode + accent presets + custom color + (admin) white-label; Light
and System work across every core view with no unreadable text; dark mode is byte-for-byte
today's look; the choice persists cross-browser via `/settings`; a white-labeled instance
shows the custom name/mark on login, sidebar, and tab title.

## Out of scope

- **Per-workspace accents** (ServerKit's `workspace_accent`) — needs product thought about
  which wins; revisit after workspaces get heavier use.
- **High-contrast / custom user themes.** Modes + accent is the surface area users asked for.

## ServerKit source map (for implementers)

- Token sheet (all three selector blocks + light values): `frontend/src/styles/_theme-variables.scss`
- Mode + accent application, matchMedia listener, white-label state: `frontend/src/contexts/ThemeContext.jsx`
- Settings UI (mode previews, presets grid, color input): `frontend/src/components/settings/AppearanceTab.jsx`
- Appearance styling: `frontend/src/styles/pages/_settings.scss` (`.theme-option`, `.accent-preset`)
