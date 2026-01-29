# DeviceKit Roadmap

What's built, what's missing, and what's next.

---

## Current State

**Working today:**
- Fleet dashboard with auto-refresh, device registry, utilization metrics
- Node detail with live diagnostics (CPU, RAM, temp, battery), ADB shell, macro quick-actions
- Remote ADB terminal with file explorer, command presets, device filesystem browsing
- Pipeline build viewer with failure analysis and demo data fallback
- Full automation system: 14 step types, visual editor, background execution, live run monitoring, cancellation
- Backend: 10 mixins, 30+ REST endpoints, thread-safe queues, alerts, activity logging
- Docker and Docker Compose for prod and dev

**Partially built / placeholder:**
- Node detail phone mockup says "WAITING FOR STREAM..." (screenshot endpoint exists but isn't wired to the UI)
- Remote ADB has Logcat Stream and Network Sniffer tabs but they're empty placeholders
- Settings page has a nav link ("SamanLabs Config") but no view component
- DynamoDB and S3 mixins exist but nothing persists to them -- all data is in-memory and lost on restart
- Pipeline/builds system is minimal, mostly demo data

---

## Phase 1 -- Persistence & Stability

Everything is in-memory right now. A restart wipes automations, runs, alerts, activities, queues, and config. This is the most critical gap.

### 1.1 Wire DynamoDB persistence into all data stores
- Automations CRUD → `devicekit_automations` table
- Automation runs → `devicekit_automation_runs` table
- Alerts → `devicekit_alerts` table
- Activities → `devicekit_activities` table
- Queues → `devicekit_queues` table
- Config → `devicekit_config` table
- Auto-create tables on startup via `ensure_table_exists()`

### 1.2 Add error recovery and reconnection
- Retry logic for ADB connections that drop
- Graceful handling when a device disconnects mid-automation
- Auto-reconnect UIAutomator2 sessions after device reboot

### 1.3 Backend health monitoring loop
- Background thread that periodically checks all connected devices
- Auto-generate alerts for low battery, overheating, disconnection, storage full
- Track device uptime and connection history

---

## Phase 2 -- Live Streaming & WebSockets

Polling every 1.5-10 seconds works but doesn't scale and feels sluggish. Real-time push is the fix.

### 2.1 Add WebSocket support (Flask-SocketIO)
- New mixin: `WebSocketMixin`
- Events: `device_status`, `automation_progress`, `alert_created`, `activity_logged`, `chat_message`
- Frontend: replace all polling intervals with socket listeners
- Fallback to polling if WebSocket connection fails

### 2.2 Live device screen stream
- Wire the existing `screenshot` endpoint into a periodic capture loop (1-2 fps)
- Push frames over WebSocket as base64 PNG or MJPEG stream
- Display in the NodeDetail phone mockup (replace "WAITING FOR STREAM...")
- Add click-to-interact: click on the stream image → send tap(x, y) to device

### 2.3 Logcat streaming
- New backend endpoint: `GET /devices/:id/logcat` (WebSocket or SSE)
- Stream `adb logcat` output in real-time
- Frontend: fill the Logcat Stream tab in Remote ADB
- Add log level filtering (V/D/I/W/E/F) and text search

### 2.4 Network traffic monitor
- Capture `adb shell dumpsys netstats` or `tcpdump` output
- Parse and display in the Network Sniffer tab
- Show per-app data usage, active connections

---

## Phase 3 -- Chat System

A real-time chat interface for team communication, device notes, and automation notifications. This ties into the WebSocket layer from Phase 2.

### 3.1 Backend chat infrastructure
- New mixin: `ChatMixin`
- DynamoDB table: `devicekit_chat_messages`
- Data model:
  ```
  {
    id: uuid,
    channel: "general" | "device:<device_id>" | "automation:<automation_id>",
    sender: { name, avatar_initials },
    message: string,
    type: "text" | "system" | "alert" | "image",
    attachments: [{ name, url, type }],
    timestamp: epoch,
    edited_at: null,
    reactions: {}
  }
  ```
- Channels:
  - `general` -- team-wide chat
  - `device:<id>` -- per-device discussion thread (notes, issues, history)
  - `automation:<id>` -- automation-specific discussion
- API endpoints:
  - `GET /chat/channels` -- list channels with unread counts
  - `GET /chat/channels/:channel/messages?before=&limit=50` -- paginated history
  - `POST /chat/channels/:channel/messages` -- send message
  - `PUT /chat/messages/:id` -- edit message
  - `DELETE /chat/messages/:id` -- delete message
  - `POST /chat/messages/:id/reactions` -- add reaction

### 3.2 Real-time message delivery
- WebSocket event: `chat_message` (new message broadcast to channel subscribers)
- WebSocket event: `chat_typing` (typing indicator)
- Join/leave channel management via socket rooms
- Unread count tracking per channel per user

### 3.3 Frontend chat view
- New view: `Chat.jsx` at route `/chat`
- New nav item under a "Collaboration" section in the sidebar
- Layout:
  - Left panel: channel list (General, device channels, automation channels)
  - Center: message thread with infinite scroll
  - Message input with shift+enter for newline
- Message rendering: text, system messages (styled differently), alert cards, image previews
- Typing indicator ("Juan is typing...")
- Unread badge on sidebar nav item
- Emoji reactions on hover

### 3.4 System-generated messages
- Auto-post to `device:<id>` when:
  - Device connects/disconnects
  - Alert triggered (battery, temp, etc.)
  - ADB command executed
  - Reboot initiated
- Auto-post to `automation:<id>` when:
  - Automation run starts/completes/fails
  - Step fails with error details
  - Run cancelled
- Auto-post to `general` for:
  - New device joined fleet
  - Critical alerts
  - Build completions

### 3.5 Device notes integration
- In NodeDetail view, add a "Notes" tab or collapsible panel
- Shows the `device:<id>` chat channel inline
- Quick-add notes without leaving the device page
- Search device history (commands run, alerts, notes)

---

## Phase 4 -- Settings & Configuration UI

The nav link exists but there's no page.

### 4.1 Settings view
- New view: `Settings.jsx` at route `/settings`
- Sections:
  - **Fleet Configuration**: default device IDs, ADB timeout, refresh intervals
  - **AWS Configuration**: region, table prefix, S3 bucket (read-only display of env vars)
  - **Alert Thresholds**: battery %, temperature, storage % triggers
  - **Automation Defaults**: default timeout per step, max concurrent runs
  - **Notification Preferences**: which events trigger chat system messages
- Persist via `/config` endpoint backed by DynamoDB

### 4.2 User management (basic)
- For now, no auth -- just user profiles stored in config
- Name, initials, role label
- Used for chat sender identity and activity attribution
- Stored in localStorage + synced to backend config

---

## Phase 5 -- Pipeline & CI Integration

The pipeline view exists but is mostly demo data.

### 5.1 Real test execution engine
- Define test suites as collections of automations
- Run a suite across multiple devices in parallel
- Aggregate results into a build record
- Track pass/fail/skip per test per device

### 5.2 Build artifacts and reporting
- Store screenshots from failed steps in S3
- Generate HTML test report per build
- Link failure analysis to specific step results and screenshots

### 5.3 Webhook triggers
- `POST /pipeline/webhook` -- trigger builds from CI systems (GitHub Actions, Jenkins)
- Callback URL for build completion notifications
- Status badges endpoint for README integration

### 5.4 Scheduled runs
- Cron-style scheduling for automation suites
- Backend scheduler thread (APScheduler or similar)
- UI for creating/editing schedules
- Run history with scheduling context

---

## Phase 6 -- Multi-Node & Fleet Scaling

Currently the backend runs on a single machine with locally connected devices.

### 6.1 Remote node agent
- Lightweight agent that runs on each machine with connected devices
- Registers with a central DeviceKit server
- Forwards ADB/UIAutomator2 commands over HTTP/WebSocket
- Reports device status and health

### 6.2 Central orchestrator
- Aggregate devices from multiple nodes
- Route automation runs to the correct node
- Load-balance test suites across available devices
- Node health monitoring and failover

### 6.3 Device groups and tagging
- Assign devices to groups (e.g., "QA", "Staging", "Production")
- Tag devices with metadata (OS version, model, location)
- Filter and target automations by group/tag
- Fleet-wide bulk operations

---

## Phase 7 -- Quality & Developer Experience

### 7.1 Testing
- Backend unit tests (pytest) for each mixin
- API integration tests with test client
- Frontend component tests (Vitest + Testing Library)
- E2E tests with a mock device (Playwright or Cypress)

### 7.2 API documentation
- OpenAPI/Swagger spec auto-generated from Flask routes
- Swagger UI served at `/docs`
- Postman collection export

### 7.3 Logging and observability
- Structured JSON logging
- Request/response logging middleware
- Frontend error boundary with error reporting
- Optional Sentry integration

### 7.4 Developer onboarding
- `.env.example` with all variables documented
- Seed script to populate demo data (devices, automations, sample runs)
- One-command setup: `docker-compose up` with everything working out of the box

---

## Phase 8 -- Advanced Automation Features

### 8.1 Conditional logic and loops
- New step types: `if_element_exists`, `loop_n_times`, `loop_until`
- Branch execution based on device state
- Retry failed steps with configurable count

### 8.2 Automation templates and sharing
- Save automations as reusable templates
- Import/export automations as JSON
- Template library with common workflows (login, clear data, smoke test)

### 8.3 Variables and parameterization
- Define variables per automation (e.g., `{{username}}`, `{{password}}`)
- Prompt for variable values at run time
- Step output piping: use output of one step as input to the next

### 8.4 Visual flow builder
- Replace linear step list with a node-based canvas (React Flow)
- Drag connections between steps
- Visualize branches, loops, and parallel paths
- Zoom, pan, minimap

---

## Priority Order

| Priority | Phase | Why |
|----------|-------|-----|
| 1 | Phase 1 -- Persistence | Data loss on restart makes everything else pointless |
| 2 | Phase 2 -- WebSockets | Foundation for chat, streaming, and real-time UX |
| 3 | Phase 3 -- Chat | Depends on WebSocket layer, adds collaboration |
| 4 | Phase 4 -- Settings UI | Low effort, fills a visible gap |
| 5 | Phase 7 -- Quality | Tests and docs before adding more features |
| 6 | Phase 5 -- Pipeline | Real CI value, builds on automation engine |
| 7 | Phase 8 -- Advanced Automations | Power-user features |
| 8 | Phase 6 -- Multi-Node | Scale-out, only needed with multiple machines |

---

## Cleanup Items (Do Anytime)

- [ ] Remove hardcoded "SamanLabs" references (sidebar nav, config)
- [ ] Replace "serviceserpapi" S3 bucket default with a configurable value
- [ ] Wire screenshot display into NodeDetail phone mockup (already has the endpoint)
- [ ] Replace simulated CPU usage in NodeDetail with real `dumpsys cpuinfo` data
- [ ] Add proper error toasts/notifications in the frontend (currently silent failures)
- [ ] Add loading skeletons to views that fetch data on mount
- [ ] Make user card in sidebar dynamic (currently hardcoded "Juan Denis")
