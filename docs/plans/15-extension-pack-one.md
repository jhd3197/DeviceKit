# Plan 15 — Extension Pack One: Browser, File Explorer, Notification Capture

**Status:** 🚧 in progress — Phase 1 ✅, Phase 2 ✅ (`devicekit-browser` CDP driver + pool routing; live-verified on a real phone)
**Inspired by:** ServerKit validated its plugin platform by shipping real builtin plugins
against it; DeviceKit's platform (plans 03/04) shipped with exactly one —
`devicekit-webhook-notify`. This plan builds the first *device-facing* extensions and, in
doing so, stress-tests every contribution point the platform claims to support.
**Depends on:** 03/04 (extension platform — shipped), 13 (AI gate — shipped; extension
write tools are always gated). Soft: 05 (jobs/schedules) for notification polling,
06 (notification bus) for forwarding captured device notifications.

## The questions this plan answers

- **"How do extensions actually work for device features?"** Three extensions, each
  exercising a different platform muscle: `devicekit-browser` (backend blueprint + AI
  tools + step types over a wire protocol), `devicekit-explorer` (a builtin extension
  shipping a real frontend page — the first user of the builtin-frontend sync path
  beyond webhook-notify's settings panel), and `devicekit-notification-capture`
  (extension-owned tables + jobs/schedules + forwarding into the plan-06 bus).
- **"Do these need to install an app on the device?"** No. All three compose
  capabilities the device already has: Chrome, the filesystem, and the agent's
  notification listener. Extensions that *provision* third-party apps (VPN drivers)
  need a `device_requirements` manifest concept and APK pinning — explicitly deferred
  (see Out of scope).
- **"What does a device-scoped extension API look like?"** The convention this plan
  establishes: `POST /ext/<slug>/devices/<device_id>/<verb>`. Extensions never invent
  their own device addressing — the `device_id` path segment mirrors core routes, and
  the SDK's permission-gated `device_control` (backend/devicekit_sdk, plan 03) is the
  only way to touch hardware.
- **"Playwright, but for a phone?"** Yes — and *not* via UI tapping. Chrome on Android
  exposes the Chrome DevTools Protocol over an abstract unix socket
  (`localabstract:chrome_devtools_remote`), reachable with
  `adb forward tcp:<port> localabstract:chrome_devtools_remote`. The backend already
  owns adb for every pooled device, so an extension can drive the device's real Chrome
  programmatically: navigate, read the DOM, evaluate JS, screenshot. No selectors tied
  to app versions, no coordinate guessing — CDP is a stable protocol, which is the
  whole reason this beats accessibility-tree automation for web tasks.

## Extension 1 — `devicekit-browser` (CDP driver)

**Category:** `automation` · **Permissions:** `adb`, `device.control`, `network`

The core is a small CDP client: `GET http://127.0.0.1:<port>/json` lists targets
(plain HTTP), then commands go over the per-target WebSocket (`Page.navigate`,
`Runtime.evaluate`, `Page.captureScreenshot`, `DOM.getDocument`/`Runtime.evaluate`
with `document.documentElement.outerHTML` for content). One pip dependency:
`websocket-client` — this is a **builtin** extension, so it goes in the backend's
requirements rather than through the `DEVICEKIT_ALLOW_EXTENSION_PIP` gate.

**Session model.** A browser session per device: allocate a local port from a pool,
`adb forward`, launch Chrome via intent if it isn't foreground (the
`chrome_devtools_remote` socket only exists while Chrome runs), connect, and record
the session in `ext_browser_sessions` (device serial, port, target id, created_at).
Teardown removes the forward. Sessions are idempotent — `ensure_session(device_id)`
is the internal entry every verb goes through, so callers never manage lifecycle.

**HTTP API** (blueprint at `/ext/devicekit-browser`):

| Route | Verb | Does |
|---|---|---|
| `/devices/<id>/session` | POST / DELETE | open / close the CDP session |
| `/devices/<id>/goto` | POST | navigate `{url}`, wait for load event |
| `/devices/<id>/content` | GET | `?format=html\|text\|title` current page |
| `/devices/<id>/evaluate` | POST | run `{expression}` in page, return value |
| `/devices/<id>/screenshot` | GET | CDP screenshot (full-page capable, unlike screencap) |
| `/devices/<id>/tabs` | GET | list open targets |

**Pool routing — the round-robin endpoint.** The headline feature: treat N devices as
one browser farm. A **pool** is a named set of devices plus a strategy, defined in
extension config (or via `POST /pools`): membership is either an explicit serial list
("select x devices"), `all`, or — the DeviceKit-native option — an **FQL query**
(plan 20), e.g. `status = online and battery > 30`, re-evaluated on each dispatch so
devices join/leave the rotation as their state changes.

| Route | Verb | Does |
|---|---|---|
| `/pools` | GET / POST | list / create pools `{name, devices\|fql\|all, strategy}` |
| `/pools/<name>/fetch` | POST | one-shot: pick next device → goto `{url}` → return `{html\|text\|screenshot, device_id}` |
| `/pools/<name>/goto` | POST | like fetch but leaves the session open; returns a `session_token` |
| `/pools/<name>/status` | GET | rotation order, per-device health/busy state, last-used timestamps |

Dispatch rules that make it production-shaped rather than a toy:

- **Strategies:** `round_robin` (default), `random`, `least_recently_used`. The cursor
  lives in the pool row, so rotation survives restarts.
- **Busy = skip:** one Chrome per device means concurrency 1 per device; a device with
  an active session is skipped, not queued behind.
- **Failover:** device offline or CDP connect fails → mark unhealthy (cooldown), retry
  the next device transparently; the response always says which `device_id` served it.
- **Sticky sessions:** multi-step flows (login → navigate → scrape) must stay on one
  device for cookies to make sense — the `session_token` from `/goto` pins subsequent
  calls to that device until released or timed out. Round-robin applies to *new*
  sessions and one-shot `fetch`es only.

**AI tools** (namespaced `devicekit_browser__*`; write tools always gated per plan 13):
`goto` (write), `evaluate` (write), `get_content` (read), `get_url` (read),
`screenshot` (read), plus the pool-aware `fetch_url` (write — dispatches through a
pool, returns content + which device served it). **Step types:** `browser_goto`, `browser_assert_text` (fail the
automation if the page text doesn't match), `browser_evaluate` (result into a step
variable), `browser_screenshot`.

**Caveats to encode as checks, not surprises:** the CDP socket requires Chrome to be
installed and running (verify via `list_installed_apps` + target list; return a clear
"Chrome not available" error); WebView-based apps expose
`webview_devtools_remote_<pid>` only when the app is debuggable — out of scope, Chrome
only; one CDP client per target (close stale connections on reconnect).

## Extension 2 — `devicekit-explorer` (device file manager)

**Category:** `utility` · **Permissions:** `filesystem`, `device.control`

Core already serves `GET /devices/<id>/files` (list), `/files/search`,
`/files/upload`, `/files/download` (`backend/devicekit/routes/device_control.py:196–287`),
and the *agent* has an on-device file manager (Phase 9) — but the DeviceKit dashboard
has **no file UI at all**, and the API is missing the destructive verbs. droidlink
covers scripting; this extension is the dashboard surface.

**Backend blueprint** fills the API gaps rather than editing core — deliberately, as a
dogfood test of "can an extension deliver a complete feature without touching host
code": `DELETE /devices/<id>/files` (path in body), `POST .../files/mkdir`,
`POST .../files/rename` (also covers move), `GET .../files/preview` (bounded-size
image/text preview for the UI). All through `sdk.device_control` so the permission
gate stays honest.

**Frontend** — the first real builtin frontend contribution beyond a settings panel:
a `Files` tab on NodeDetail (`node-detail.tabs` slot, seeded in plan 04) plus a
`contributions.routes` page. Breadcrumb navigation, list/grid with size + mtime,
upload (drag-drop onto the table), download, image preview, delete/rename with
`useConfirm`. Ships via `scripts/sync-builtin-frontends.mjs` and its `--check` CI gate.

**AI tools:** `list_files` (read), `read_text_file` (read, size-capped),
`delete_file` (write — gated, as a destructive tool should be). No new step types:
core `push`/`pull` steps already exist.

## Extension 3 — `devicekit-notification-capture`

**Category:** `monitoring` · **Permissions:** `device.control`, `network`

The agent advertises a notification-listener capability that **nothing consumes** —
`can.notification_listener` exists as an FQL field
(`backend/devicekit/mixins/fleet_query.py:41,504`) and the agent has
`NotificationRoutes`, but no backend feature reads device notifications. This
extension closes that loop, and it unlocks the single most valuable automation
primitive a phone fleet has: **reading OTP/2FA codes**.

**Capture pipeline.** A scheduled job (the `jobs` + `schedules` contribution points,
plan 05 — first real external user) polls each capable device's notification feed and
appends new items to `ext_notification_capture_events` (device serial, package, title,
text, posted_at, dedup key). Config schema: package allowlist, regex filters,
retention days, poll interval. If profiling shows polling is too coarse for OTP
latency, a follow-up can add agent-side push over the existing agent↔backend sync
channel — start with polling because it needs zero APK changes.

**The killer step type — `wait_for_notification`:** package + title/text regex +
timeout; on match, extracts the first capture group into an automation variable. That
turns "log into app X" from impossible to a five-step automation: `open_app` →
`type_text` (credentials) → `wait_for_notification` (`(\d{6})` from the SMS app) →
`type_text` (`{{otp}}`) → `assert`.

**AI tools:** `recent_notifications` (read), `wait_for_notification` (read — it
mutates nothing on the device; it blocks with a bounded timeout).

**Bus forwarding:** matched notifications emit a catalog event through the extension
`notification_events` contribution (already wired — `mixins/extensions.py:684`), so
plan-06 channels — including `devicekit-webhook-notify` — deliver them. Extensions
composing through the bus, not importing each other.

## Platform work this plan carries (small, and only what the pack needs)

1. **Wire `automation_templates`** — the manifest key is validated
   (`extension_manifest.py:128`) but connected to nothing (EXTENSIONS.md:104). Wire it
   so activation registers ready-made automations (marked with their source slug,
   removed on uninstall). Each pack extension ships one: browser — "open URL, assert
   text, screenshot"; explorer — none (UI-only is fine); notification-capture — the
   OTP login skeleton above.
2. **Registry entries** — add all three to `backend/devicekit/data/registry_index.json`
   as builtins alongside webhook-notify, with real sha256s (unlike the placeholder
   `devicekit-appium` entry).
3. **Docs** — EXTENSIONS.md gains a "device-scoped API convention" section
   (`/ext/<slug>/devices/<device_id>/...`) and drops the stale "jobs/notify raise
   NotImplementedError" text (plans 05/06 landed).

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 ✅ | `automation_templates` wiring + scaffolder `--full` mode (`scripts/new_extension.py`) | reserved manifest seam becomes real |
| 2 ✅ | `devicekit-browser`: CDP session core → device API → pool routing (round-robin, FQL membership, sticky sessions) → AI tools + step types | wire-protocol extension; gated write tools; fleet-level dispatch |
| 3 | `devicekit-explorer`: backend verbs → frontend Files tab/page | builtin frontend path end-to-end |
| 4 | `devicekit-notification-capture`: poller → tables → `wait_for_notification` → bus forwarding | jobs/schedules + extension tables + bus composition |
| 5 | registry entries, EXTENSIONS.md updates, template automations | marketplace shows a real catalog |

**Phase 1 notes (as shipped).** `automation_templates` is now seeded at activation
(`extensions.py:_register_automation_templates`) — each template JSON (relative to the
extracted backend dir) becomes an automation tagged `ext:<slug>`, idempotently (safe on every
boot/enable), removed on uninstall (`_remove_automation_templates`), left in place on disable.
Two platform fixes rode along, both required by the pack: (a) the `jobs`/`schedules` manifest
keys were *validated* as inline lists but *activated* as `module:func` strings — an
unusable contradiction; activation now consumes the documented inline-list form
(`[{kind, handler}]` / `[{name, kind, interval_seconds, …}]`), which phase 4 depends on;
(b) the SDK's `device_control` gained permission-gated `forward()`/`remove_forward()` (adb
port-forward), which phase 2's CDP driver needs. The scaffolder grew a `--full` mode that
emits the device-scoped `/ext/<slug>` blueprint plus models/ai_tools/jobs/schedules/an
automation template. Proof: `backend/tests/test_automation_templates.py` (4 tests); full
suite 178 passed. The three extensions are scaffolded fresh in their own phases (2–4) so each
manifest and its code always match.

**Phase 2 notes (as shipped).** `devicekit-browser` mounts at `/ext/devicekit-browser` and
ships: a small CDP client (`cdp.py`, dep `websocket-client`), per-device sessions
(`sessions.py`), pool routing (`pools.py`), the device + pool blueprint (`routes.py`), four
`browser_*` step types, six `devicekit_browser__*` AI tools (writes gated), and the seeded
"open, assert, screenshot" automation. Three things reality forced that the plan didn't call
out, all verified live on the Samsung A03s: (1) **Chrome 111+ rejects CDP WebSocket handshakes
with a disallowed `Origin` header** → the client connects with `suppress_origin=True`. (2) **A
bare LAUNCHER intent leaves Chrome with no drivable page target, and Android freezes background
tabs**, so a session creates and pins a *dedicated* tab via `Target.createTarget`, brings it to
front each op, and closes it on teardown — driving an arbitrary pre-existing tab hangs. (3) Two
small platform enhancements the pack needed: extension AI tools that declare a `device_id`
parameter now get it injected (hidden from the LLM schema) so per-device tools work, and the
automation engine gained run-scoped variables (`store_as` on any step + `{{name}}`
interpolation) — the mechanism the OTP flow (phase 4) and `browser_evaluate` rely on. Pools
resolve membership from an explicit serial list, `all`, or a live-re-evaluated FQL query;
round-robin persists its cursor. Proof: `tests/test_browser_extension.py` (6 tests, incl.
round-robin dispatch + AI-tool binding) + a live end-to-end run (create target → navigate →
title/text/`evaluate`=42/PNG screenshot → reuse across ops → close). Live driving needs a phone
with Chrome; the unit tests stub the device fleet.

Phases 2–4 are independent of each other (parallelizable after phase 1); phase 5 last.

## Out of scope (deferred deliberately, with their prerequisites named)

- **`devicekit-serp`** — search executed in the device's real Chrome and scraped from
  the DOM. It's the natural *consumer* of `devicekit-browser`, which makes it the
  first extension-depends-on-extension case: it needs a `requires_extensions` manifest
  key plus an SDK seam for calling another extension's API. Do it as a follow-up once
  browser is stable — the dependency mechanism is a platform decision worth its own
  moment.
- **App-driver extensions (VPN etc.)** — need `device_requirements` (declared package
  + pinned APK version/sha256, surfaced on the consent card) and version-keyed
  selector packs, since they automate third-party UIs that drift with app updates.
- **Third-party frontend loading** — still builtin-only, per the plan 04 / ServerKit
  ADR 0001 decision. Explorer being builtin is what makes its UI possible.
