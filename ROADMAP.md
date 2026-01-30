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

---

## Upcoming Phases

### Phase 12: Multi-Device Fleet Management
**Goal**: Manage multiple Android devices simultaneously.

- [ ] Backend device grouping (tags, labels)
- [ ] Bulk actions: install APK on all devices, run command on group
- [ ] Device comparison view (metrics side-by-side)
- [ ] Fleet health dashboard with aggregate metrics
- [ ] Auto-onboarding: detect new ADB device → offer to install agent APK

### Phase 13: Automation Engine
**Goal**: Visual workflow builder for device automation.

- [ ] Step types: tap, swipe, wait, screenshot, shell command, file operation, assertion
- [ ] Automation recorder: record actions on device → generate steps
- [ ] Schedule automations (cron-like)
- [ ] Automation results with pass/fail per step + screenshots
- [ ] Share automations between devices

### Phase 14: Security & Production Hardening
**Goal**: Secure all communication channels.

- [ ] Agent HTTP server authentication (API key / token)
- [ ] HTTPS support for agent ↔ backend communication
- [ ] Backend authentication (JWT or API key)
- [ ] Rate limiting on all endpoints
- [ ] Audit logging for all device actions
- [ ] Agent app signing for release builds

### Phase 15: CI/CD Integration
**Goal**: Use DeviceKit in CI/CD pipelines.

- [ ] droidlink pytest plugin for test framework integration
- [ ] GitHub Actions workflow templates
- [ ] Pipeline view: map to real CI builds
- [ ] Test result reporting with screenshots on failure
- [ ] Device allocation for parallel test execution

### Phase 16: Prompture Integration — Device Personalities & Conversational Agents
**Goal**: Replace direct Anthropic/OpenAI calls with Prompture for multi-provider conversations, tool use, memory, and structured output. Devices become persistent conversational agents with personalities.

- [ ] Add `prompture` to backend dependencies
- [ ] Create `PromptureAgentMixin` replacing raw AI calls with `Conversation` + `ToolRegistry`
- [ ] Register droidlink device actions as Prompture tools (tap, swipe, type, press, open_app, screenshot)
- [ ] Per-device `Conversation` instances with system prompts built from profile (personality, niche, interests)
- [ ] Conversation memory: device remembers prior interactions across agent cycles
- [ ] Multi-provider support via Prompture drivers (switch between Claude, GPT-4, Groq, Ollama, etc. per device)
- [ ] Structured action output via Pydantic models instead of raw JSON parsing
- [ ] `UsageSession` per device for token/cost tracking on the dashboard
- [ ] `DriverCallbacks` hooks for real-time agent observability (log every AI request/response)
- [ ] Streaming responses via `ask_stream()` for live "thinking" feedback on frontend
- [ ] Conversation export/import for persistence across backend restarts
- [ ] Frontend: model selector per device profile, token usage display, conversation history view
- [ ] API endpoints: `/devices/:id/conversation/history`, `/devices/:id/conversation/clear`, `/devices/:id/agent/usage`

See [prompture_integration.md](./prompture_integration.md) for full technical design.
