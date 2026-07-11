# Architecture

Read this first. DeviceKit is **four components working as one platform**, and everything else in
these docs assumes you know how they fit together.

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeviceKit Platform                        │
├─────────────┬──────────────┬────────────────┬───────────────────┤
│  Frontend   │   Backend    │   droidlink    │  Agent (Android)  │
│  React/Vite │  Flask API   │  Python lib    │  Kotlin app       │
│  port 5173  │  port 5050   │  (pip install) │  port 9800 / 9801 │
└──────┬──────┴──────┬───────┴───────┬────────┴────────┬──────────┘
       │             │               │                 │
       │  REST+SSE   │  merges ADB   │  direct device  │  register +
       │  dashboard  │  + agent into │  control via    │  heartbeat +
       │  subscribes │  one /devices │  agent's HTTP   │  state up to
       │  to events  │  fleet        │  server         │  the backend
       └─────────────┴───────────────┴─────────────────┘
```

- The **backend** is the hub. It owns durable state, orchestrates device actions, and is the only
  component the frontend talks to.
- The **frontend** is a pure client of the backend — REST for actions, SSE for real-time updates.
- The **agent** runs on each phone. It reports up to the backend *and* exposes its own on-device
  HTTP server that droidlink talks to directly.
- **droidlink** bypasses the backend entirely for device control — it drives the agent's on-device
  server over USB or WiFi. It only touches the backend to report CI test results.

The rest of this doc walks each component, then the data flow that ties them together.

---

## 1. Backend — a mixin-composed Flask app

`backend/` is a single-process Python/Flask application. Its heart is one class, `Client`
(`backend/devicekit/client.py`), assembled from **31 feature mixins** — each mixin owns one
capability, and composing them produces the full service layer. `app.py` instantiates `Client`
and serves it.

```python
class Client(
    PersistenceMixin,      # SQLAlchemy engine + migrations (must be first)
    AdbMixin,              # adb command wrapper
    Uiautomator2Mixin,     # uiautomator2 automation + agent-APK install
    CdpMixin,              # Chrome DevTools Protocol
    DynamodbMixin, AwsStorageMixin,   # optional AWS blob/archive backends
    AutomationMixin,       # automation CRUD, runs, steps, schedules
    ProfileMixin,          # per-device AI profiles
    NLAutomationMixin,     # AI generate / refine / explain / self-heal
    PromptureAgentMixin,   # per-device conversational AI agent
    AgentGateMixin,        # AI confirmation gate + session modes
    FleetMixin, FleetQueryMixin, DeviceLockMixin,   # groups, FQL, locking
    StreamingMixin, VisualRegressionMixin, DebugBundleMixin,
    AgentDeviceMixin,      # live agent registry + command dispatch
    PairingMixin,          # pairing-code enrollment
    ExtensionsMixin,       # the extension platform
    JobsMixin, NotificationsMixin, MetricsHistoryMixin, SettingsMixin,
    EventsMixin,           # SSE broadcast helper
    ApiAppMixin,           # build_app() — the Flask factory
    QueueMixin, AlertMixin, ActivityMixin, AuthMixin,
    ToolsMixin,            # utility helpers
):
    ...
```

> The exact order is the MRO. `PersistenceMixin` is deliberately **first** (every data-owning mixin
> depends on the DB being ready); the auth and utility mixins sit at the tail. A new feature is a
> new `*Mixin` added to this list — see the `new-mixin` recipe.

### How a request is served

Routes are **Flask Blueprints**, one module per feature, in `backend/devicekit/routes/` (24
modules). Every module exposes the same factory:

```python
def make_blueprint(client, limiter) -> Blueprint: ...
```

`ApiAppMixin.build_app()` is the composition root. It:

1. creates the Flask app and applies **CORS** (`CORS_ORIGINS`),
2. builds the **rate limiter** (`flask-limiter`, 200/min default, stricter on `/adb`, `/reboot`,
   uploads, and bulk actions),
3. installs the **auth middleware** (`@before_request`) — API key for general routes, agent token
   for `/agent-device/*`, query-param fallback for SSE (disabled by default in dev),
4. adds **security headers** and **audit logging** (`@after_request`),
5. registers every blueprint via `register_all(app, client, limiter)`,
6. **hot-loads installed extensions** (`load_all_extensions(app)`),
7. **starts the job workers** (the `JobConsumer` + `JobScheduler` daemons).

`build_app()` is a factory separate from `app.run()` so the route table can be tested without
booting a server. The URL surface is stable — the frontend, the Android agent, and droidlink all
depend on these paths.

### State lives in SQLAlchemy

Durable state is **SQLAlchemy models, SQLite by default** (`backend/devicekit/db.py`,
`models/`). `PersistenceMixin` owns the engine and runs **Alembic migrations at boot** — a fresh
DB is created and stamped, an existing one is upgraded. Point `DEVICEKIT_DATABASE_URL` at Postgres
to scale out. Every mutation uses a short-lived transactional session:

```python
with db.session_scope() as s:
    s.execute(...)   # commit on success, rollback on exception, always closed
```

Automations, runs, fleet groups, saved FQL queries, visual baselines, debug-bundle metadata,
stream-session metadata, the agent-device registry, jobs, notifications, and metrics history all
persist and survive a restart. Genuinely ephemeral things — SSE client queues, MJPEG viewer
counts, in-flight run threads, the agent event ring buffer — are intentionally *not* persisted.
This "SQLAlchemy is the source of truth" decision is [ADR 0003](adr/0003-sqlalchemy-source-of-truth.md).

### Real-time is SSE, not WebSockets

There is **no Socket.IO / WebSocket** anywhere. Real-time updates ride **Server-Sent Events**
(`EventsMixin`, `backend/devicekit/mixins/events.py`):

- Any mixin calls `self.broadcast(event_type, data)`, which pushes an SSE frame onto every
  connected client's in-memory queue.
- The frontend connects to `GET /events/stream`, which yields an `event: connected` handshake and
  then streams frames, with a `: keepalive` comment every **15s**.
- Because the backend is **single-process**, the client registry is a plain in-memory list guarded
  by a lock. No multi-worker patterns — this is a deliberate constraint.

Event types you'll see on the stream include: `device_connected` / `device_new` /
`device_reconnected` / `device_disconnected`, `device_state`, `device_heartbeat`, `device_event`,
`alert`, `notification`, `job`, `pending_action` / `pending_action_resolved` (the AI gate),
`pipeline_build` / `pipeline_test`, `stream_viewer`, `bulk_action_complete`, and `agent_enrolled`.

### Background work is jobs, not loose threads

Scheduled and deferred work goes through a **SQL-backed queue + job system**
(`backend/devicekit/queue_bus/` and `jobs/`) rather than scattered daemon threads:

- `QueueBusService` — a durable queue with visibility timeouts, priority, retry with backoff, and
  a dead-letter path (a near-verbatim port of ServerKit's queue).
- `Job` rows + a single `JobConsumer` daemon that dispatches each job's `kind` to a registered
  handler on a bounded worker pool.
- `ScheduledJob` rows (interval or cron) whose `next_run_at` survives restarts, ticked by a single
  `JobScheduler`.

Automation runs, the schedule checker, bundle/job retention, and the agent heartbeat reaper all run
as jobs. Extensions can contribute their own job kinds and schedules.

### The unified `/devices` fleet

`GET /devices` (`routes/devices.py`) is where the two device worlds merge. On each request the
backend refreshes from ADB (auto-connecting and auto-onboarding the agent APK to new serials),
then folds in every **agent-registered** device from the in-memory registry (`AgentDeviceMixin`),
marking each `online` if its last heartbeat is under 15s old. The result is one `{devices, count}`
list regardless of how each device is attached.

*(Note: `device_manager.py` is a separate CDP/ADB port pool used for parallel test allocation — not
the `/devices` composite.)*

---

## 2. Frontend — React client of the backend

`frontend/` is **React 18 + Vite + Tailwind** (dark theme). It is a thin client:

- **Every API call goes through `frontend/src/api.js`** — one centralized client. No component
  fetches directly.
- **Real-time** state comes from `subscribeToEvents()` in `api.js`, an SSE client for
  `/events/stream`. Views subscribe for live device state, run progress, notifications, and the AI
  gate; REST is the fallback for initial load.
- `App.jsx` is the router + sidebar. Views live in `src/views/` (Dashboard, NodeDetail, Pipeline,
  Automations, Fleet, Settings, Extensions, and more).
- In dev, Vite proxies `/api` to `http://127.0.0.1:5050`, so the frontend and backend need no CORS
  fuss locally.

**Extensions contribute UI declaratively.** The frontend fetches
`GET /extensions/contributions` and renders extension-provided nav items, routes, and widgets with
no edits to `App.jsx`. Only **builtin** extensions ship frontend code (compiled into the bundle);
third-party extensions contribute backend + step types, which get a free editor UI. That delivery
model is [ADR 0002](adr/0002-no-third-party-frontend-code.md). See the
[Extension Guide](extensions/guide.md) for the whole picture.

---

## 3. Agent — the on-device Kotlin app

`agent-android/` is a Kotlin app (`com.devicekit.agent`) that turns a phone into a first-class
fleet member. When its `BackgroundAgent` foreground service runs it does two independent jobs:

- **Reports up to the backend** — registers, then sends heartbeats (5s) and full state/metrics
  (2s) to `/agent-device/*`. If the backend is unreachable it drops to **standalone mode** and
  keeps serving locally.
- **Serves an on-device HTTP API on port 9800** (NanoHTTPD) — input, screen capture, files, shell,
  app management, notifications, streaming, and more. This is what droidlink drives directly. It
  also answers **UDP discovery probes on port 9801** so droidlink can find it over WiFi.

The agent relies on an accessibility service (UI state) and a notification-listener service
(status-bar notifications). The exact registration, heartbeat, state, and command protocol —
including HMAC signing and pairing enrollment — is specified in **[Fleet Contract](FLEET_CONTRACT.md)**.
That doc is the spec for building a non-Kotlin agent.

---

## 4. droidlink — the Python client library

[`droidlink`](https://pypi.org/project/droidlink/) (`pip install droidlink`) is a standalone Python
library in its [own repo](https://github.com/jhd3197/droidlink). It talks **directly to a device's
agent HTTP server** — USB via `adb forward`, WiFi via UDP discovery — so it needs no backend for
device control:

```python
import droidlink
d = droidlink.connect("<SERIAL>")     # USB
d(text="Login").click()
d.screenshot("screen.png")
```

It ships a CLI and a **pytest plugin** whose `device` / `device_pool` fixtures allocate devices and
report results back to the DeviceKit backend's pipeline API. It kept the `droidlink` name rather
than `devicekit` — [ADR 0004](adr/0004-droidlink-name-on-pypi.md). See the
[droidlink guide](droidlink.md) for fleet usage and [CI/CD Setup](ci-setup.md) for pipelines.

---

## The connection flow

How a device goes from "plugged in" to "streaming metrics in the dashboard":

1. **Agent app** starts its `BackgroundAgent` service on the phone.
2. Agent tries to **register** with the backend: `POST /agent-device/register`.
3. If the backend is reachable, the agent sends **heartbeats every 5s** and **state every 2s**.
4. If the backend is **not** reachable, the agent runs **standalone** — its on-device HTTP server
   (port 9800) still works, so droidlink can control the device directly with no backend at all.
5. **droidlink** connects straight to the agent's HTTP server:
   - USB: `adb forward tcp:9800 tcp:9800` → `http://127.0.0.1:9800`
   - WiFi: `http://<device-ip>:9800`, auto-discovered via UDP 9801
6. **Backend** merges ADB-connected devices + agent-registered devices into one `/devices` list.
7. **Frontend** subscribes to the backend SSE stream (`/events/stream`) for real-time device
   state, with REST as the initial-load fallback.

### Why the agent stays on "Connecting…"

The agent shows "Connecting…" when its service is running but it can't reach the backend at the
configured URL (default `http://127.0.0.1:5050`). Over USB, the phone's `127.0.0.1:5050` only
routes to your machine after a reverse tunnel:

```bash
adb -s <SERIAL> reverse tcp:5050 tcp:5050
```

Without the backend the agent still works standalone — droidlink can control the device over port
9800 regardless.

---

## Conventions worth internalizing

These hold across the whole backend — match them when you extend it:

- **JSON errors** are `{'error': 'message'}` with a non-200 status code.
- **List responses** are `{'<resource>': [...], 'count': N}`.
- **IDs** are `uuid.uuid4()`; **timestamps** are `time.time()` (epoch seconds).
- **Real-time is SSE** via `self.broadcast(...)` — never WebSockets.
- **The backend is single-process** — no multi-worker assumptions; in-process state (SSE queues,
  run threads) lives in the one process by design.
- **Route URLs are stable** — the frontend, the Kotlin agent, and droidlink all depend on them.

---

## Where to go deeper

| Topic | Doc |
| --- | --- |
| Agent ↔ backend protocol (register/heartbeat/state/commands, HMAC, pairing, capabilities) | [Fleet Contract](FLEET_CONTRACT.md) |
| The AI layer (agent, tools, confirmation gate, session modes, NL automation) | [AI Agent](ai-agent.md) |
| Building an extension | [Extension Guide](extensions/guide.md) |
| Driving devices from Python / CI | [droidlink](droidlink.md) · [CI/CD Setup](ci-setup.md) |
| Why it's built this way | [Decision records](README.md#decision-records) |
| Full phase-by-phase history | [ROADMAP.md](../ROADMAP.md) · [docs/plans/](plans/00-overview.md) |
