# DeviceKit Roadmap

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeviceKit Platform                       │
├─────────────┬──────────────┬────────────────┬───────────────────┤
│  Frontend   │   Backend    │   droidlink    │  Agent Android    │
│  React/Vite │  Flask API   │  Python lib    │  Kotlin app       │
│  port 3000  │  port 5050   │  (library)     │  port 9800/9801   │
└──────┬──────┴──────┬───────┴───────┬────────┴────────┬──────────┘
       │             │               │                 │
       │  REST API   │               │   HTTP/USB      │
       ├─────────────┤               ├─────────────────┤
       │             │               │                 │
       │  Dashboard  │  Registers +  │  Direct device  │
       │  subscribes │  heartbeats   │  control via    │
       │  to SSE     │  from agent   │  agent HTTP     │
       │  stream     │  every 5s     │  server         │
       │             │               │                 │
       │             │  Merges ADB   │  USB: ADB port  │
       │             │  + agent      │    forwarding   │
       │             │  devices      │  WiFi: direct   │
       │             │               │    IP:9800      │
       └─────────────┴───────────────┴─────────────────┘
```

### Connection Flow

1. **Agent app** starts BackgroundAgent service on the phone
2. Agent tries to register with backend at `POST /agent-device/register`
3. If backend is reachable, agent sends heartbeats (5s) and state reports (2s)
4. If backend is NOT reachable, agent runs in **standalone mode** — the embedded HTTP server (port 9800) still works for direct droidlink control
5. **droidlink** (Python) connects directly to the agent's HTTP server:
   - USB: `adb forward tcp:9800 tcp:9800` then `http://127.0.0.1:9800`
   - WiFi: `http://<device-ip>:9800` (auto-discovered via UDP 9801)
6. **Backend** merges ADB-connected devices + agent-registered devices into a unified `/devices` list
7. **Frontend** subscribes to backend SSE stream (`/events/stream`) for real-time device state, with REST fallback for initial load

### Why "Connecting..." stays forever

The agent shows "Connecting..." when `BackgroundAgent.isRunning == true` but `DeviceState.isConnected == false`. This means the agent service is running but cannot reach the backend server at the configured URL (default `http://127.0.0.1:5050`).

**To connect**: The backend Flask server (`python backend/app.py`) must be running on port 5050. If testing locally with a USB-connected phone, ADB reverse-forward is needed:
```bash
adb reverse tcp:5050 tcp:5050
```
This makes the phone's `127.0.0.1:5050` route to the computer's port 5050.

**Without backend**: The agent works standalone. droidlink can control the device directly via port 9800 without needing the backend at all.

---

## Completed Work

### Phase 1: Project Scaffolding ✅
- Directory structure, configs, Docker setup
- Backend mixin architecture ported from CrawlerAndroid
- Frontend React/Vite/Tailwind shell

### Phase 2: Backend Core ✅
- ADB, UIAutomator2, CDP, DynamoDB, S3 mixins
- Device manager with thread-safe pool
- Flask API with agent registration + heartbeat endpoints

### Phase 3: Backend New Mixins ✅
- Queue, Alerts, Activity, Profile mixins
- Agent device state management and merging

### Phase 4: API Layer ✅
- Full REST API: devices, dashboard stats, automations, profiles, alerts
- Agent communication endpoints (register, state, heartbeat, commands)
- Agent APK serving endpoint

### Phase 5: Frontend Shell ✅
- App.jsx with sidebar navigation
- Dashboard, NodeDetail, Pipeline, RemoteADB views
- Automations, Profiles, Settings views
- api.js centralized client

### Phase 6: Frontend Views ✅
- All views wired to backend API
- Device list with real-time metrics
- Node detail with diagnostics and ADB shell

### Phase 7: Android Agent App ✅
- Background service with foreground notification
- State reporting (keyboard, window, clipboard, metrics, notifications)
- Embedded HTTP server (NanoHTTPD, port 9800) with routes:
  - `/files/*` (list, read, write, delete, mkdir, rename)
  - `/tap`, `/swipe`, `/press` (input)
  - `/screenshot` (screen capture)
  - `/shell` (command execution)
  - `/app/*` (app management)
  - `/metrics`, `/clipboard`, `/notifications`
- UDP discovery service (port 9801)
- Accessibility service for UI state monitoring
- Notification listener service

### Phase 8: droidlink Python Library ✅
- Connection module (USB via ADB, WiFi direct)
- Device class with manager composition
- File, Shell, Input, Screen, App, Clipboard, Notifications, Metrics managers
- UI automation (element, selector)
- Events, Gestures, Streaming, Logcat, Intents, Settings, Contacts
- CLI tool
- Auto-discovery via UDP broadcast

### Phase 9: Agent UI — Navigation Drawer + File Manager ✅
- Replaced TabLayout with hamburger/drawer navigation
- Swipeable tabs for Dashboard, Metrics, Logs (ViewPager2)
- Drawer-only sections for Files, Settings
- File manager: storage picker (Internal + SD Card), permission handling
- Back navigation through directory tree
- CPU metrics fix (cpufreq-based reading for sandboxed apps)
- RAM display formatting (GB instead of raw MB)

### Phase 10: End-to-End Connection & File Operations ✅
- Test Connection button in Settings with green/red status feedback
- Server URL save on Enter key press
- ADB reverse guide shown when localhost connection fails, with copy command button
- Network discovery: device WiFi IP display + subnet scan (20 concurrent, 1s timeout)
- Agent `/files/search` endpoint (recursive walk, max depth 10, case-insensitive)
- Agent `/files/upload` endpoint (multipart POST, NanoHTTPD temp file handling)
- droidlink `post_file()` with `_ProgressReader` for upload progress callbacks
- droidlink `get_bytes_streamed()` with `iter_content()` download progress
- `FileManager.search()`, `FileManager.upload()` with progress support
- `FileManager.pull()` updated with optional progress callback
- droidlink CLI: `files list`, `files search`, `files upload`, `files pull` subcommands
- Backend `device_files()` tries agent HTTP first, falls back to ADB
- Backend proxy routes: `/files/search`, `/files/upload`, `/files/download`
- Frontend: search bar in Device Explorer, upload via UploadCloud icon, file download on click

### Phase 11: Agent ↔ Backend Real-Time Sync ✅
- SSE broadcast infrastructure: `/events/stream` endpoint with in-memory queue-per-client, 15s keepalive
- Broadcast hooks on all agent endpoints: `device_connected`, `device_state`, `device_heartbeat`, `device_event`, `device_disconnected`
- Auto-alert generation from agent metrics: low battery (<20%), overheating (>45°C), storage full (<5% free) with 5-minute dedup
- Frontend `subscribeToEvents()` SSE client in `api.js`
- Dashboard: replaced 10s polling with SSE, live connection indicator (green/red), real CPU + battery mini-bars per device row
- NodeDetail: SSE subscription for real-time diagnostics (2s updates), polling fallback reduced to 30s, battery level chart added alongside CPU/RAM

### Phase 12: Multi-Device Fleet Management ✅
**Goal**: Manage multiple Android devices simultaneously.

- [x] Backend `FleetMixin`: device group CRUD, per-device tags, group membership
- [x] Fleet API: 15 new endpoints — group CRUD, bulk actions, device tags, fleet health, device compare
- [x] Bulk actions: run shell command, install agent APK, reboot — all on device groups with per-device results
- [x] Fleet health endpoint: aggregate CPU/battery/RAM/temp averages, health distribution (healthy/warning/critical)
- [x] Device comparison view: select up to 4 devices, real-time SSE-updated step charts (CPU, RAM, Battery)
- [x] Fleet Groups view: create/edit groups with color picker, tag input, device checklist; bulk action dialog with results table
- [x] Dashboard: fleet health metric cards, health distribution bar (emerald/amber/red), auto-onboarding toast notifications
- [x] Auto-onboarding: `device_new` SSE event on agent registration → blue toast with "Install Agent" button (15s auto-dismiss)
- [x] Navigation: "Device Groups" and "Compare" links in sidebar under Management

### Phase 13: Automation Engine ✅
**Goal**: Visual workflow builder for device automation.

- [x] `file_operation` step type: push/pull/delete files via ADB in automation steps
- [x] Automation recorder: Record button in NodeDetail captures tap/swipe/press actions → generates automation steps → opens editor
- [x] Schedule automations: interval-based scheduling with background checker thread, schedule CRUD, pause/resume/delete from Automations view
- [x] Screenshot on failure: auto-captures device screenshot when a step fails, clickable thumbnail in run detail with full-size overlay
- [x] Share automations: clone (deep copy with new UUIDs), export as JSON file download, import from JSON file upload

### Phase 14: Security & Production Hardening ✅
**Goal**: Secure all communication channels.

- [x] `AuthMixin`: API key + agent token validation, disabled by default for dev (set `API_KEY` / `AGENT_TOKENS` env vars to enable)
- [x] `before_request` auth middleware: API key for general endpoints, agent token for `/agent-device/*`, query-param fallback for SSE
- [x] Rate limiting via `flask-limiter`: 200/min default, stricter limits on `/adb` (30), `/reboot` (5), `/files/upload` (20), `/bulk/*` (10)
- [x] Security headers on all responses: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`
- [x] CORS lockdown: `CORS_ORIGINS` env var respected (defaults to `*` for dev)
- [x] Audit logging: `after_request` hook auto-logs all POST/PUT/DELETE with `source_ip` and `authenticated` status
- [x] Debug mode toggle: `DEBUG_MODE` env var controls Flask debug/reloader
- [x] Frontend auth propagation: `X-API-Key` header on all requests, SSE auth via query param, `uploadFile` auth
- [x] droidlink auth: optional `api_key` param on `Connection`, `connect_usb`, `connect_wifi` (sets `X-Agent-Token` header)
- [ ] Agent-side HTTPS/token support (deferred — requires Kotlin changes + APK rebuild)
- [ ] Agent app signing for release builds (deferred)

### Phase 15: CI/CD Integration ✅
**Goal**: Use DeviceKit in CI/CD pipelines.

- [x] `DeviceLockMixin`: thread-safe device allocation with auto-expiring locks for parallel test runners
- [x] Device lock API: `POST /devices/<id>/lock`, `POST /devices/<id>/unlock`, `GET /devices/available`
- [x] Enhanced pipeline build lifecycle: `created → running → completed/failed` with UUID IDs, source tracking, CI URL
- [x] Test result reporting: `POST /pipeline/builds/<id>/tests` (single) and `.../tests/bulk` (batch) with SSE broadcast
- [x] Failure screenshots: `POST` with `screenshot_b64` → `GET /pipeline/builds/<id>/screenshots/<index>` serves PNG
- [x] `pytest-droidlink` plugin: `device` and `device_pool` fixtures, `DroidLinkReporter` with fire-and-forget backend calls
- [x] Plugin CLI options: `--device`, `--device-wifi`, `--devicekit-url`, `--devicekit-api-key`, `--no-report`, `--screenshot-on-failure`
- [x] Plugin hooks: session start/finish (build lifecycle), `pytest_runtest_makereport` (per-test reporting with screenshot capture)
- [x] `pyproject.toml` entry point: `pytest11` → `droidlink.pytest_plugin`
- [x] Frontend Pipeline view: real API data, 5s polling + SSE, loading/empty states, status badges, CI link, screenshot modal, stats bar
- [x] Frontend API: `updateBuildStatus`, `getBuildScreenshot`, `getAvailableDevices`, `lockDevice`, `unlockDevice`, SSE `pipeline_test`/`pipeline_build`
- [x] GitHub Actions workflow template: `.github/workflows/device-tests.yml` (self-hosted runner, pytest, JUnit artifacts, dorny/test-reporter)
- [x] CI setup documentation: `docs/ci-setup.md` (runner requirements, secrets, WiFi config, device locking conftest example, troubleshooting)

### Phase 16: Prompture Integration — Device Personalities & Conversational Agents ✅
**Goal**: Replace direct Anthropic/OpenAI calls with Prompture for multi-provider conversations, tool use, memory, and structured output. Devices become persistent conversational agents with personalities.

- [x] Add `prompture>=0.0.36` to backend dependencies, remove direct `anthropic` dep
- [x] Create `PromptureAgentMixin` replacing raw AI calls with `Conversation` + `ToolRegistry`
- [x] Register device actions as Prompture tools (tap, swipe, type_text, press_key, open_app)
- [x] Per-device `DeviceConversation` instances with system prompts built from profile (personality, niche, interests, behavior)
- [x] Conversation memory: device remembers prior interactions across agent stop/start cycles
- [x] Multi-provider support via Prompture drivers (switch between Claude, GPT-4, Groq, Ollama, Google per device)
- [x] `DeviceAction` Pydantic model for structured action output instead of raw JSON parsing
- [x] `UsageSession` per device for token/cost tracking (prompt_tokens, completion_tokens, total_cost, call_count, errors)
- [x] `DriverCallbacks` hooks for real-time agent observability (record every AI request/response/error)
- [x] `PROMPTURE_DEFAULT_MODEL` config + `.env.example` with multi-provider API key placeholders
- [x] Profile schema: `model_name` field in create/update for per-device model selection
- [x] API endpoints: `GET /devices/:id/conversation/history`, `DELETE /devices/:id/conversation`, `GET /devices/:id/agent/usage`, `PATCH /devices/:id/agent/model`
- [x] Frontend NodeDetail: model badge, usage panel (tokens/cost/calls), model selector dropdown, conversation history toggle, clear conversation button
- [x] Frontend Dashboard: Fleet AI Cost metric card aggregating cost across all active agents
- [x] Frontend ProfileEditor: AI Model section with 5 presets + custom input
- [ ] Streaming responses via `ask_stream()` for live "thinking" feedback on frontend (deferred)
- [ ] Conversation export/import for persistence across backend restarts (deferred)

See [prompture_integration.md](./prompture_integration.md) for full technical design.

---

### Phase 17: Natural Language Automation Builder ✅
**Goal**: Bridge the Prompture AI layer and the automation engine so users can describe automations in plain English and get executable step sequences. Add self-healing capabilities to automation steps.

- [x] `NLAutomationMixin`: AI-powered generate, refine, explain, UI hierarchy fetch, and self-heal methods using Prompture `Conversation` with `UsageSession`
- [x] `POST /automations/generate` endpoint: accepts `{ description, device_id }`, returns generated automation steps with explanation via Prompture
- [x] Prompture system prompt with full automation step schema (all 14 step types with config schemas) so LLM generates valid steps
- [x] `POST /automations/refine-step` endpoint: modify a single step with natural language instruction
- [x] `GET /automations/<id>/explain` endpoint: AI summarizes what an automation does in plain English
- [x] `GET /devices/<id>/ui-hierarchy` endpoint: fetch accessibility tree from device via agent HTTP or uiautomator2 fallback
- [x] Self-healing automation steps: when a UI-targeting step fails (`tap_by_text`, `tap_by_resource_id`, `wait_for_element`, `assert_element`), captures UI hierarchy + error context, asks Prompture to re-locate the target element and retries
- [x] `self_heal` flag on `execute_automation()` and `POST /automations/<id>/run` body, propagated through run record to thread
- [x] Heal result tracking in step results: `healed`, `original_step`, `healed_step`, `heal_reasoning` fields
- [x] Frontend AutomationEditor: collapsible "Generate with AI" panel with NL textarea, optional device context selector, preview steps with Accept All / Replace All / per-step accept/reject
- [x] Frontend per-step refinement: inline "Refine with AI" wand icon on each step, text input for instruction, updates step in place
- [x] Frontend Automations: "Enable self-healing" checkbox toggle in Run dialog with HeartPulse icon and tooltip
- [x] Frontend Automations: Lightbulb "Explain" button per automation card, modal with AI-generated explanation
- [x] Frontend AutomationRunDetail: amber "Self-healed" badge with HeartPulse icon, reasoning text, original vs healed config diff; red "Heal failed" badge for unsuccessful attempts
- [x] Frontend API client: `generateSteps`, `refineStep`, `explainAutomation`, `getUiHierarchy` methods + updated `runAutomation` with `selfHeal` param

### Phase 18: Real-Time Device Streaming ✅
**Goal**: Replace screenshot polling with live video streaming for a true remote desktop experience. Enable session recording and playback.

- [x] `StreamingMixin`: MJPEG stream proxy (`/devices/<id>/stream`) bridges frontend to agent `/screen/stream`, viewer counting with thread-safe lock
- [x] Frontend `StreamCanvas` component: `<canvas>` rendering via `useMjpegStream` hook, replaces `<img>` screenshot polling in NodeDetail, 15-30fps via `fetch` + `ReadableStream`
- [x] Adaptive quality: three presets (low 5fps/30q, medium 15fps/50q, high 30fps/80q) selectable in NodeDetail, plus stream on/off toggle
- [x] Touch overlay: SVG ripple animation on tap/click with `animate-ping`, rendered on canvas overlay layer
- [x] Session recording: `POST /devices/<id>/sessions/record` + `POST .../stop`, background capture thread saves JPEG frames to temp directory, event recording via `POST .../events`
- [x] Session playback: frame-by-frame `<img>` playback with timeline scrubber (`<input type="range">`), event markers as dots on timeline, speed control (0.5x/1x/2x)
- [x] Frontend Sessions panel: collapsible panel listing recorded sessions per device with frame count, duration, fps, event count; click to play
- [x] Multi-viewer support: `_stream_viewers` counter tracks concurrent connections, `stream_viewer` SSE event broadcasts viewer count, `<Users>` badge shown when >1 viewer
- [x] Latency indicator: color-coded (green <100ms, yellow <300ms, red >300ms) latency + fps display in top-right overlay on active stream
- [x] Fallback: `StreamCanvas` auto-detects stream failure, degrades to 1s `<img>` screenshot polling with amber "POLLING" badge; retries stream periodically
- [x] Auth: MJPEG stream endpoint supports `api_key` query param fallback (streams can't send custom headers)
- [x] Keyboard shortcuts and input gestures updated: removed manual `setScreenTs` refresh (stream is live), coordinate mapping works with canvas element

---

### Phase 19: Visual Regression Testing ✅
**Goal**: Add screenshot-based assertions to automations so tests can verify what they see, not just what they do. Use AI to distinguish meaningful UI changes from noise.

- [x] `screenshot_assert` step type in `STEP_TYPES`: captures screenshot and compares against stored baseline, configurable `baseline_id`, `threshold` (default 95%), and `use_ai` toggle
- [x] `VisualRegressionMixin`: in-memory baseline storage with UUID IDs, version tracking, per-device-model + resolution baselines, mask region support
- [x] Baseline CRUD API: `POST /automations/:id/baselines` (capture from device or upload b64), `GET` list with thumbnails, `GET /:id/image` serves JPEG, `PUT` re-capture/update masks, `DELETE`
- [x] Pixel-diff engine: PIL-based grayscale SSIM computation with configurable threshold, mask region exclusion, block-based diff region detection (16px blocks)
- [x] AI-powered diff analysis: when SSIM < threshold, sends context to Prompture with `AI_DIFF_SYSTEM_PROMPT`, returns verdict (pass/fail/needs_review), confidence score, meaningful changes vs noise classification; high-confidence AI pass overrides pixel verdict
- [x] Diff regions: `_compute_diff_regions()` returns `{x, y, w, h, intensity}` blocks highlighting changed areas
- [x] Mask regions: drag-select on baseline preview image to mark ignore areas (clocks, ads, dynamic content), stored per-baseline, excluded from SSIM computation
- [x] Multi-device baselines: `find_baseline()` prefers exact device_model + resolution match, falls back to model-only, then any; `capture_baseline()` auto-detects device model and resolution
- [x] `GET /automations/:id/baselines` — list all baselines with thumbnails (version, device model, mask count, step index), grid display in AutomationEditor
- [x] Regression report: `GET /automations/runs/:id/regression-report` summarizes all `screenshot_assert` results (passed/failed/needs_review counts), collapsible panel in AutomationRunDetail with color-coded summary bar
- [x] Frontend AutomationEditor: baseline capture mode — Camera icon on `screenshot_assert` steps, device selector dialog, captured baselines displayed in grid with preview overlay, mask drawing mode
- [x] Frontend AutomationRunDetail: violet "Visual pass"/"Visual fail" badges on `screenshot_assert` step results, regression report panel with per-assertion breakdown
- [x] `POST /automations/:id/baselines/:id/compare` endpoint for on-demand baseline comparison with device screenshot

---

## Phase 20: Fleet Query Language ✅
**Goal**: Enable SQL-like queries across the device fleet for filtering, reporting, and bulk action targeting.

- [x] Query DSL parser: tokenizer + recursive descent parser — supports `android_version < 13 AND battery > 20 AND status = 'idle'` with proper operator precedence (OR < AND < NOT < comparison)
- [x] Supported fields: `device_id`, `model`, `manufacturer`, `android_version`, `sdk`, `battery`, `cpu`, `ram_used`, `ram_total`, `temperature`, `online`, `status`, `agent_status`, `group`, `tags`, `model_name` — with smart fallbacks for ADB vs agent device data
- [x] Operators: `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE` (SQL pattern with `%` and `_`), `IN`, `NOT IN`, `AND`, `OR`, parentheses for grouping — case-insensitive string comparison, automatic type coercion
- [x] `GET /fleet/query?q=<expression>` endpoint: evaluates query against merged ADB + agent device state, returns matching devices with count and total
- [x] Frontend: query bar on Dashboard with field autocomplete (shows field descriptions), run/clear buttons, real-time result count, error display
- [x] Query → bulk action: `POST /fleet/query/bulk-action` pipes query results into bulk operations — supports reboot, lock, unlock, install_apk, run_automation, add_tag, remove_tag, add_to_group — with per-device success/failure tracking
- [x] Saved queries: full CRUD via `POST/GET/PUT/DELETE /fleet/queries` to save, list, update, and delete named queries with validation
- [x] Frontend: saved query dropdown with delete, preset query dropdown (All offline, Low battery, Critical health, Idle devices, Running devices, Outdated Android), save current query button
- [x] Query validation: `POST /fleet/query/validate` validates expressions without executing, `GET /fleet/query/fields` returns field metadata, `GET /fleet/query/presets` returns built-in presets
- [x] Fleet reports: `GET /fleet/query?q=...&format=csv` exports query results as downloadable CSV with Content-Disposition header, frontend Export CSV button
- [x] Bulk action UI: dropdown on query results with reboot, lock, unlock, add_tag, add_to_group actions with parameter prompts and success/failure summary

---

## Phase 21: Failure Debug Bundles ✅
**Goal**: When a test or automation step fails, auto-package all relevant diagnostics into a single downloadable bundle for fast debugging.

- [x] `DebugBundleMixin`: collects screenshot, logcat (last 100 lines), device state (CPU/RAM/battery/active app), UI hierarchy XML, last 10 agent actions, and device properties — packaged into in-memory ZIP with base64 storage
- [x] Auto-trigger: bundle auto-generated on automation step failure (`trigger='automation_failure'`) with full context (automation_id, run_id, step_index, step_type, error); also supports manual request and pipeline trigger
- [x] `POST /devices/<id>/debug-bundle` endpoint: on-demand bundle generation with configurable trigger and context, runs retention cleanup on each generation
- [x] `GET /debug-bundles/<id>/download` endpoint: download bundle as ZIP (screenshot.png, logcat.txt, state.json, ui_hierarchy.xml, actions.json, properties.json), plus `GET /debug-bundles` for listing and `GET /debug-bundles/<id>` for metadata
- [x] Automation integration: `_run_automation_thread` in AutomationMixin auto-generates bundle on step failure, stores `debug_bundle_id` in step result dict for frontend access
- [x] Pipeline integration: bundle generation available via `POST /devices/<id>/debug-bundle` with `trigger='pipeline_failure'` — can be called by DroidLinkReporter
- [x] AI failure analysis: `POST /debug-bundles/<id>/analyze` sends bundle text contents (logcat, state, UI hierarchy, actions) to Prompture for root cause hypothesis, severity assessment, and suggested fix
- [x] Frontend AutomationRunDetail: orange "Debug Bundle" panel on failed steps with Download ZIP button, AI Analysis trigger button with inline analysis display, and Share button
- [x] Frontend api.js: 8 new API methods — generateDebugBundle, listDebugBundles, getDebugBundle, downloadDebugBundleUrl, analyzeDebugBundle, shareDebugBundle, sharedBundleUrl, deleteDebugBundle
- [x] Bundle retention policy: `cleanup_old_bundles(max_age_days=30)` auto-removes bundles and associated share tokens older than retention period, triggered on manual bundle generation
- [x] Shareable bundle URL: `POST /debug-bundles/<id>/share` generates time-limited token (default 24h), `GET /debug-bundles/share/<token>` validates expiry and serves ZIP download, frontend copies link to clipboard

---

## Upcoming Phases

### Phase 22: Predictive Device Health
**Goal**: Use historical device metrics to predict failures before they happen and surface proactive alerts on the dashboard.

> Design doc: [docs/plans/08-metrics-history.md](docs/plans/08-metrics-history.md). Note: the plan supersedes the DynamoDB choice below in favor of the Phase 23 SQLite persistence layer, and this phase builds on Phases 23 + 25.

- [ ] `MetricsHistoryMixin`: persist device metrics (CPU, RAM, battery, temperature, storage) to DynamoDB at configurable intervals (default 5min)
- [ ] `GET /devices/<id>/metrics/history?hours=24` endpoint: return time-series metrics data for charting
- [ ] Battery degradation tracking: compare charge capacity over time, detect batteries holding less charge than baseline
- [ ] Storage fill rate: linear projection of when device will run out of storage based on recent consumption trend
- [ ] Thermal throttling detection: flag devices with sustained temperature above threshold, correlate with CPU performance drops
- [ ] Predictive alerts: new alert types — `battery_degraded`, `storage_fill_predicted`, `thermal_pattern`, `device_unreliable` (frequent disconnects)
- [ ] Health score: composite 0-100 score per device based on battery health, storage headroom, thermal history, uptime stability
- [ ] `GET /fleet/health/predictions` endpoint: list all devices with active predictions and estimated time-to-issue
- [ ] Frontend Dashboard: "Predictions" card showing devices at risk with estimated timeline ("Device X: storage full in ~3 days")
- [ ] Frontend NodeDetail: metrics history charts (24h/7d/30d) for CPU, RAM, battery, temperature, storage
- [ ] Fleet-wide trends: `GET /fleet/metrics/trends` — aggregate metrics across fleet over time (avg battery health declining, storage usage growing)
- [ ] Anomaly detection: flag devices deviating significantly from fleet averages (e.g., one device running 30% hotter than peers)

---

## Platform Evolution Phases (ServerKit-inspired)

Phases 23–34 come from the plan set in [docs/plans/](docs/plans/00-overview.md) — concepts harvested from ServerKit and adapted to DeviceKit. Each phase links its detailed plan doc; a local executor prompt (`docs/plans/prompt.md`, git-ignored) can drive any of them end-to-end. The dependency graph lives in the overview; numbering is the suggested order, but the frontend phases (30–32) and packaging (34) can run in parallel with the backend track.

### Phase 23: Persistence Layer ✅
**Goal**: Durable state — nothing user-created is lost on a backend restart.
See [docs/plans/01-persistence-layer.md](docs/plans/01-persistence-layer.md).

- [x] SQLAlchemy + SQLite foundation: `db.py` engine/session, `models/` package, `DEVICEKIT_DATABASE_URL` (Postgres-ready), Alembic migrations at boot
- [x] `PersistenceMixin` owning session lifecycle, registered before data-owning mixins
- [x] Migrate saved FQL queries + fleet groups/tags, then automations + schedules
- [x] Migrate runs + step results, visual baselines, debug-bundle metadata, stream-session metadata
- [x] Migrate agent-device registry rows (coordinates with Phase 29)
- [x] Response envelopes unchanged so the frontend needs zero edits

### Phase 24: API Blueprint Refactor
**Goal**: Split the ~2,100-line `api_app.py` into per-feature Flask Blueprints — the mounting surface the extension platform requires.
See [docs/plans/02-api-blueprint-refactor.md](docs/plans/02-api-blueprint-refactor.md).

- [ ] `backend/devicekit/routes/` package: one module per current section header, each exposing `make_blueprint(client)`
- [ ] Extract the SSE broadcast helper first; move `api_app()` closure state onto mixins
- [ ] `api_app()` reduced to app factory + CORS/limiter/auth + blueprint registration
- [ ] Route-table snapshot diff proves URLs are byte-identical before/after

### Phase 25: Jobs, Queue Bus & Scheduler
**Goal**: Replace scattered daemon threads with persisted jobs, retries, and DB-defined schedules.
See [docs/plans/05-jobs-and-queue.md](docs/plans/05-jobs-and-queue.md).

- [ ] Port ServerKit's SQL-backed queue (visibility timeouts, priority, retry, dead-letter)
- [ ] `Job` rows + single `JobConsumer` daemon + `kind → handler` registry
- [ ] `ScheduledJob` rows (cron or interval) with restart-surviving `next_run_at`
- [ ] Move automation runs and the schedule checker onto jobs; keep SSE progress events
- [ ] Jobs API + a recent/failed jobs panel in the UI

### Phase 26: Extension Platform — Backend
**Goal**: Installable extensions contributing step types, FQL fields, AI tools, routes, jobs, and tables.
See [docs/plans/03-extension-platform-backend.md](docs/plans/03-extension-platform-backend.md).

- [ ] `extension.json` manifest spec + validator + `InstalledExtension` rows
- [ ] Install pipeline: preview/consent → pinned sha256 → Zip-Slip-safe extract → hot-load blueprint
- [ ] Status guard (disabled extension routes return 503 without restart) + boot loader + self-heal
- [ ] `devicekit_sdk` façade with declaration-based permission gate; `ext_<slug>_*` table namespacing with keep-vs-purge uninstall
- [ ] Step-type dispatch registry (retire the `_execute_step` elif chain) + FQL field + Prompture tool registration
- [ ] `devicekit-extensions` registry repo (index.json + schema + validators + CI), fetch with offline fallback chain
- [ ] First builtin extracted from core (visual regression) + scaffolding CLI + author docs

### Phase 27: Extension Platform — Frontend & Marketplace
**Goal**: Extensions contribute nav, routes, and widgets declaratively; users browse/install from a marketplace view.
See [docs/plans/04-extension-platform-frontend.md](docs/plans/04-extension-platform-frontend.md).

- [ ] Contributions envelope endpoint consumption: nav + routes + page titles, per-extension error boundaries
- [ ] `ExtensionSlot` mount points (dashboard, run detail, settings) with SVG sanitization
- [ ] Marketplace view: browse (builtin + registry), consent chips, installed management, schema-driven config forms, keep-vs-purge uninstall
- [ ] `devicekit-sdk` Vite alias with versioned surface; builtin frontend sync script + CI drift gate

### Phase 28: Notification Bus
**Goal**: Fleet events reach operators — in-app, webhook, and email — with preferences and history.
See [docs/plans/06-notification-bus.md](docs/plans/06-notification-bus.md).

- [ ] Event catalog (`device.offline`, `automation.run.failed`, `automation.run.healed`, `regression.detected`, `device.battery.critical`, …)
- [ ] Producer + persisted deliveries + queue-driven channel consumers; in-app channel over existing SSE
- [ ] Bell dropdown with unread badge + optimistic mark-read; `/notifications` history view
- [ ] Webhook (Slack/Discord-compatible) channel, then email; per-event preferences + quiet hours

### Phase 29: Agent Security & Fleet Registry
**Goal**: Authenticated agents, principled offline detection, audited commands, capability-based targeting.
See [docs/plans/07-agent-security-and-fleet-registry.md](docs/plans/07-agent-security-and-fleet-registry.md).

- [ ] Registry extraction from `api_app.py` closures + `AgentDevice`/`DeviceCommand` persistence
- [ ] Heartbeat reaper with reconnect-race fixes (identity re-check under lock; fail in-flight commands on reconnect)
- [ ] HMAC request signing + nonce replay guard + timestamp window (closes the deferred Phase 14 items; requires APK update)
- [ ] Pairing-code enrollment flow (agent shows code, dashboard claims) + key rotation
- [ ] Capability map → FQL fields, `require_capability` step type, capability-filtered device pickers

### Phase 30: Frontend Foundations
**Goal**: Shared primitives so views stop duplicating tables, empty states, and fetch wiring.
See [docs/plans/09-frontend-foundations.md](docs/plans/09-frontend-foundations.md).

- [ ] `DataTable` + `EmptyState` + `useConfirm` + toast provider (adopt in Automations list)
- [ ] `api.js` split into domain modules behind an unchanged `api.*` surface
- [ ] `ListPage` + `Set`-based bulk selection wired to `/fleet/query/bulk-action`
- [ ] URL-as-state hooks (`useTabParam`), SSE hooks (`useEvents`/`useDeviceState`), terminal input queue for RemoteADB

### Phase 31: Command Palette & Dashboard Widgets
**Goal**: `Ctrl+K` jump-to-anything; a dashboard users compose themselves.
See [docs/plans/10-command-palette.md](docs/plans/10-command-palette.md) and [docs/plans/11-dashboard-widgets.md](docs/plans/11-dashboard-widgets.md).

- [ ] cmdk palette: pages + devices + automations + actions, fuzzy scoring, recents
- [ ] FQL mode (`>` prefix) running fleet queries inline from the palette
- [ ] Dashboard carved into widgets with a renderer map; toggle/reorder/reset persisted in localStorage with forward-compatible merge
- [ ] Extension entries (palette) + extension widgets (`dashboard.top` slot)

### Phase 32: Settings & Theming
**Goal**: A real `/settings` (the sidebar link currently 404s) and runtime accent theming.
See [docs/plans/12-settings-and-theming.md](docs/plans/12-settings-and-theming.md).

- [ ] Settings shell at `/settings/:tab` with URL-driven tabs; General / API / About panes
- [ ] AI (Prompture provider/model), Streaming, and Debug-Bundle panes backed by a settings table
- [ ] Notification preferences pane (with Phase 28) + extension settings slot (with Phase 27)
- [ ] Accent color ramp via CSS variables mapped into Tailwind; persisted preference

### Phase 33: AI Confirmation Gate
**Goal**: A human between the LLM and the hardware — write tools require approval.
See [docs/plans/13-ai-confirmation-gate.md](docs/plans/13-ai-confirmation-gate.md).

- [ ] Annotate device tools read vs write; confirmation gate blocks write tools pending approval (SSE `pending_action` + confirm endpoint, timeout = deny)
- [ ] Session modes: observe / supervised / autonomous, with per-device defaults in Profiles
- [ ] Approval cards in the NodeDetail chat; audit trail of every executed tool call
- [ ] Extension AI tools always gated; supervised self-heal option (pause run, notify, resume on approval)

### Phase 34: Python Library Publishing ✅
**Goal**: Publish the Python client library to PyPI under one clean install name.
See [docs/plans/14-devicekit-python-package.md](docs/plans/14-devicekit-python-package.md).

**Outcome (2026-07-09)**: PyPI's name-similarity policy blocks the bare name `devicekit` (conflicts with the unrelated `device-kit` project — nobody else can claim it either), so the library kept its original brand.

- [x] Library extracted to its own public repo: [jhd3197/droidlink](https://github.com/jhd3197/droidlink)
- [x] Published to PyPI as [`droidlink` 0.1.0](https://pypi.org/project/droidlink/) — `pip install droidlink`
- [x] PyPI Trusted Publishing workflow on `v*` tags (activate by adding the publisher on pypi.org + a `pypi` environment on the repo)
- [x] PyPI README quickstart; monorepo README/docs/CI now install `droidlink` from PyPI
