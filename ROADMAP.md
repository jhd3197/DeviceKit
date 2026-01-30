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
       │  polls      │  heartbeats   │  control via    │
       │  backend    │  from agent   │  agent HTTP     │
       │  every 10s  │  every 5s     │  server         │
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
7. **Frontend** polls backend for device list, metrics, and state

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

---

## Upcoming Phases

### Phase 10: End-to-End Connection & File Operations
**Goal**: Make the agent reliably connect to the backend, and enable file search/transfer between droidlink and agent.

- [ ] Add server URL configuration in agent Settings fragment (currently hardcoded to `127.0.0.1:5050`)
- [ ] Add QR code / manual IP entry for easy server discovery
- [ ] Add `adb reverse` setup guide in the UI when server is unreachable
- [ ] Implement file search endpoint in agent HTTP server (`/files/search?query=...`)
- [ ] Implement file upload endpoint in agent HTTP server (`POST /files/upload`)
- [ ] Add file transfer progress reporting
- [ ] Wire frontend RemoteADB file explorer to agent file routes
- [ ] Add droidlink CLI commands for file search (`droidlink files search <query>`)

### Phase 11: Agent ↔ Backend Real-Time Sync
**Goal**: Live device state on the frontend dashboard without polling.

- [ ] Add Server-Sent Events (SSE) endpoint on backend for real-time device updates
- [ ] Frontend subscribes to SSE for live metrics, connection status
- [ ] Agent pushes events (app install, file change, notification) in real-time
- [ ] Dashboard shows live CPU/RAM/battery charts per device
- [ ] Alert auto-generation: low battery (<20%), high temp (>45°C), storage full (<5%)

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
