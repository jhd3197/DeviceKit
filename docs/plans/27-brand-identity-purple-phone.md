# Plan 27 — Brand Identity: the Purple Phone Logo, Everywhere

**Status:** 🚧 in progress — Phase 1 ✅ (web mark everywhere), Phases 2–3 pending
**Inspired by:** ServerKit's branding pipeline — one master SVG
(`frontend/src/assets/ServerKitLogo.svg`: 2048 viewBox, white squircle tile, diagonal
indigo gradient `#6366f1 → #4f46e5`), a JSX twin (`components/ServerKitLogo.jsx`) whose
gradient reads **CSS accent variables** so the mark re-tints with the user's accent (unique
gradient id per instance via `useId()` — shared ids collide and paint nothing), a
hand-simplified 32×32 stroke favicon, and `serverkit-agent/packaging/icons/generate_icons.py`
rasterizing the master into `.ico`/tray icons.
**Depends on:** 12 (accent CSS vars — the JSX logo tints from them), 25 (soft — OTA can
ship the re-branded APK fleet-wide once phase 3 rebuilds it)

## Problem

DeviceKit has **three different marks and two different brand colors**:

- Web sidebar + login: the lucide `Layers` glyph in a white square (`App.jsx:145-149`,
  `auth/Login.jsx:16-21`) — no `Logo` component exists.
- Web favicon: a *different* custom phone-outline SVG, emerald `#10b981` on `#050505`.
- **Android agent: already the target identity** — adaptive icon with solid indigo
  `#6366F1` background + white phone glyph (`ic_launcher_background.xml` /
  `ic_launcher_foreground.xml`), app theme `colorPrimary #6366F1`, dark purple surfaces
  (`#0F0D1A` / `#1E1B2E`).

The "og logo" ask = make the agent's purple-tile-with-phone the canonical mark, draw it
properly as one master SVG in ServerKit's style, and roll it out to every surface.

## Design for DeviceKit

### Part 1 — The master asset + Logo component

- `frontend/src/assets/DeviceKitLogo.svg` — ServerKit's geometry (white inset tile
  `x/y=150, 1748², rx=150`; gradient squircle ring; glyph in `brandGradient
  #6366f1 → #4f46e5` diagonal) with the server shelves replaced by a **phone**: rounded
  body, white screen cutout, speaker slot, home indicator, and the green `#3ddc97` status
  LED kept for family continuity. Starting draft (refine proportions during execution):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2048 2048">
  <defs>
    <linearGradient id="brandGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="100%" stop-color="#4f46e5"/>
    </linearGradient>
  </defs>
  <rect x="150" y="150" width="1748" height="1748" rx="150" fill="white"/>
  <!-- outer squircle ring -->
  <path fill="url(#brandGradient)" fill-rule="evenodd" d="M378,70 H1670 A308,308 0 0 1 1978,378 V1670 A308,308 0 0 1 1670,1978 H378 A308,308 0 0 1 70,1670 V378 A308,308 0 0 1 378,70 Z M450,220 A230,230 0 0 0 220,450 V1598 A230,230 0 0 0 450,1828 H1598 A230,230 0 0 0 1828,1598 V450 A230,230 0 0 0 1598,220 Z"/>
  <!-- phone body with screen cutout -->
  <path fill="url(#brandGradient)" fill-rule="evenodd" d="M804,434 H1244 A100,100 0 0 1 1344,534 V1514 A100,100 0 0 1 1244,1614 H804 A100,100 0 0 1 704,1514 V534 A100,100 0 0 1 804,434 Z M794,560 A30,30 0 0 0 764,590 V1390 A30,30 0 0 0 794,1420 H1254 A30,30 0 0 0 1284,1390 V590 A30,30 0 0 0 1254,560 Z"/>
  <rect x="944" y="481" width="160" height="32" rx="16" fill="white"/>
  <rect x="924" y="1501" width="200" height="32" rx="16" fill="white"/>
  <circle cx="1216" cy="628" r="28" fill="#3ddc97"/>
</svg>
```

- `frontend/src/components/Logo.jsx` — same paths, gradient stops wired to the accent ramp
  so the mark follows the user's accent. **Gotcha:** plan 12 stores accent vars as
  space-separated `R G B` triplets for Tailwind alpha, so stops must be
  `stopColor="rgb(var(--accent-hover, 90 103 232))"` etc., and the gradient id must come
  from `useId()` (ServerKit's collision lesson). Props: `size`, `className`.

### Part 2 — Web rollout

- Sidebar header (`App.jsx`) and Login/invite card (`auth/Login.jsx`): swap the white
  `Layers` square for `<Logo size={…}/>`. About pane gets a 64px one.
- **Favicon:** replace `frontend/public/favicon.svg` with a 32×32 stroke redraw in
  ServerKit's favicon style — gradient tile `#6d7cff → #5a67e8`, white 2px stroke phone,
  green `#3ddc97` LED:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <defs>
    <linearGradient id="dkFavTile" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
      <stop stop-color="#6d7cff"/><stop offset="1" stop-color="#5a67e8"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" rx="7" fill="url(#dkFavTile)"/>
  <g fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="10.5" y="5" width="11" height="22" rx="2.5"/>
    <line x1="14.5" y1="23.5" x2="17.5" y2="23.5"/>
  </g>
  <circle cx="23" cy="8" r="2.5" fill="#3ddc97"/>
</svg>
```

- `index.html`: icon links (svg + ico/png rasters if practical), title stays `DeviceKit`.
  Add `public/manifest.json` (name `DeviceKit`, `theme_color #4f46e5`,
  `background_color #000000`, icon `/favicon.svg` maskable) if absent.

### Part 3 — Brand color: purple becomes the default accent

- `theme.js`: `DEFAULT_ACCENT` `#10b981` → **`#6d7cff`** (ServerKit's live periwinkle;
  the static logo asset keeps the deeper `#6366f1/#4f46e5` pair — same two-purples split
  ServerKit uses). Add Periwinkle/Indigo to `ACCENT_PRESETS`; update the
  `appearance.accent` default in `SETTINGS_DEFAULTS`.
- **Semantic emerald is untouched** — plan 12's rule stands: online/pass/success stays
  `#10b981`; only brand chrome rides the accent ramp. Users with a stored accent keep it
  (settings row wins); only the default changes.

### Part 4 — Android agent alignment

- `ic_launcher_background.xml`: solid `#6366F1` → the diagonal gradient (VectorDrawable
  `<gradient>` inside the adaptive background, API 26+ — already the minimum for
  `mipmap-anydpi-v26`). Align `ic_launcher_foreground.xml`'s phone glyph with the master's
  proportions; touch `ic_notification.xml` if it drifts. App label stays `DeviceKit Agent`.
- Rebuild via the `build-agent-apk` skill; distribute through plan 25's OTA channel once
  live (until then, hand-flash — same as every agent change today).

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 ✅ | Master SVG + `Logo.jsx` + sidebar/login/About swap + favicon + manifest | one mark everywhere on web; changing the accent re-tints the sidebar logo live |
| 2 | Purple default accent (`#6d7cff`), presets updated, settings default | a fresh install boots purple; an existing user's chosen accent survives |
| 3 | Android adaptive-icon gradient + glyph alignment + APK rebuild | the launcher icon on a real device matches the web favicon family |

**Phase 1 notes (shipped):** `Logo.jsx` wires stop 1 → `--accent`, stop 2 → `--accent-dim`
(not `--accent-hover` as the plan sketched — DeviceKit's `--accent-hover` is *brighter* than
the base, which flattens the gradient; `--accent-dim` is the darker ramp stop and reproduces
the master's `#6366f1 → #4f46e5` diagonal). Sidebar/login/About render `<Logo/>` directly (no
white wrapper — the mark carries its own white tile). Raster `.ico`/png favicons skipped (SVG
link covers modern browsers; no rasterizer wired). `index.html` title normalized to `DeviceKit`.

## Decisions to make while executing (log, don't stop)

- **Sidebar tile treatment:** full `<Logo/>` mark vs ServerKit's sidebar pattern (lucide
  glyph in a small accent-gradient tile). Recommend the real `<Logo/>` at 26–32px — DeviceKit
  finally has a mark; use it.
- **Raster favicons** (`.ico`, 16/32 png): generate if a quick tool is at hand
  (sharp/cairosvg one-liner); the SVG link alone covers modern browsers — don't block on it.
- **`index.html` title** currently `DeviceKit Pro | SamanLabs` — normalize to `DeviceKit`
  (PageTitle already overrides at runtime).

## Definition of done

Sidebar, login, About, browser tab, and the Android launcher all show the same purple
phone-in-squircle family; the web mark re-tints when the accent changes; no `Layers`-as-logo
usage remains (grep `Layers` in App.jsx/Login.jsx); phase 3's APK on a physical device shows
the gradient icon.

## Out of scope

- **Light/system theme + white-label** — plan 28 (white-label will let users *replace* this
  logo; it needs `Logo.jsx` to exist first).
- **Desktop/tray icon pipeline** (ServerKit's `generate_icons.py`) — DeviceKit has no desktop
  agent; revisit if one appears.

## ServerKit source map (for implementers)

- Master SVG: `frontend/src/assets/ServerKitLogo.svg` (geometry to clone)
- JSX twin + useId gotcha: `frontend/src/components/ServerKitLogo.jsx`
- Favicon style: `frontend/public/favicon.svg`; manifest: `frontend/public/manifest.json`
- Sidebar tile alternative: `components/Sidebar.jsx:325-330` + `styles/components/_sidebar.scss:179`
- Icon rasterization reference: `serverkit-agent/packaging/icons/generate_icons.py`
