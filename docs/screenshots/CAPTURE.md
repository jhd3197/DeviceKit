# Screenshot capture

The README's **📸 Screenshots** section is generated from the PNGs in this
folder. Every shot comes from a **mock-data demo build** — no real device
serials, IPs, or account data. The whole set is reproducible with one command.

## Reproduce

```bash
cd frontend
npm install          # first time — pulls puppeteer-core
npm run shots        # boots the mock build + captures every shot
```

`npm run shots` (→ `frontend/scripts/capture-screenshots.mjs`):

1. starts the mock Vite build (`npm run dev:mock`, `vite --mode mock`), which
   loads `frontend/src/mock/` — a `window.fetch` + `EventSource` interceptor that
   serves a **fictional fleet** with no Python backend,
2. drives a headless Chrome/Edge (via `puppeteer-core`, no browser download) to
   each route, and
3. writes `docs/screenshots/<name>.png` at 1440×900 @2×.

To add/adjust the fictional data, edit `frontend/src/mock/data.js`; to add a
route or an interaction, edit the `SHOTS` list in the capture script.

## Conventions

- **Theme:** default dark theme, accent as shipped.
- **Viewport:** 1440×900, `deviceScaleFactor: 2` (retina), scrollbars hidden.
- **Data:** the mock seed only — hostnames, serials, and metrics are fictional.
- **Format:** PNG, filename exactly as listed below (kebab-case).

## Shots

| File | View | Route |
|------|------|-------|
| `dashboard.png` | Fleet Overview | `/` |
| `node-detail.png` | Node Control (incl. live-stream pane) | `/node/:id` |
| `automation-run.png` | Automation Run — per-step results, self-heal, visual assert, debug bundle | `/automations/runs/:id` |
| `automation-editor.png` | Automation Editor (step builder) | `/automations/:id/edit` |
| `workflow.png` | Workflow Builder (node canvas) | `/automations/:id/graph` |
| `automations.png` | Automations list + recent runs | `/automations` |
| `compare.png` | Device Compare | `/fleet/compare` |
| `monitor.png` | Metrics Monitor + alert rules | `/fleet/monitor` |
| `groups.png` | Device Groups | `/fleet/groups` |
| `pipeline.png` | Pipeline / CI | `/pipeline` |
| `profiles.png` | Profiles (AI personas) | `/profiles` |
| `remote-adb.png` | Remote ADB + file explorer | `/remote-adb` |
| `enrollment.png` | Enrollment / pairing | `/enrollment` |
| `command-history.png` | Command History | `/command-history` |
| `jobs.png` | Jobs | `/jobs` |
| `notifications.png` | Notifications | `/notifications` |
| `extensions.png` | Extensions (installed + registry) | `/extensions` |
| `settings.png` | Settings | `/settings` |

The **Node Control** shot doubles as the live-streaming view, and the
**Automation Run** shot covers per-step results, self-healing, visual regression,
and debug bundles in one frame — so there are no separate `stream` / `regression`
/ `debug-bundle` files. Keep this table in sync with the `SHOTS` list in the
capture script and the shot block in the README.
