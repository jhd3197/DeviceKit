# Fleet Contract — the agent ↔ backend protocol

This is the wire contract between a device **agent** and the DeviceKit **backend**: how an agent
registers, proves it's alive, streams state, receives commands, authenticates, and enrolls. The
reference implementation is the Kotlin agent in `agent-android/`, but nothing here is
Kotlin-specific — **this doc is the spec for building a non-Kotlin agent** (or debugging why one
won't enroll).

Backend source: `backend/devicekit/routes/agent_devices.py` (HTTP surface),
`backend/devicekit/mixins/agent_device.py` (registry, dispatch, HMAC),
`backend/devicekit/mixins/pairing.py` (enrollment).

---

## Transport & ports

- The backend listens on **`5050`** by default (`API_HOST=0.0.0.0`, `API_PORT=5050`). Routes carry
  **no prefix** — every path below is root-relative, e.g. `http://<backend>:5050/agent-device/register`.
- The agent's default backend URL is `http://127.0.0.1:5050`. Over USB the phone reaches your
  machine only through a reverse tunnel: `adb -s <SERIAL> reverse tcp:5050 tcp:5050`.
- All request and response bodies are **JSON**.
- Separately, the agent runs its **own** HTTP server on the device (port **9800**) and answers UDP
  discovery on **9801** — that's the surface [droidlink](droidlink.md) drives directly, *not* part
  of this contract. This doc is only the uplink to the backend.

The `device_id` is **derived server-side** at registration as
`f"{manufacturer}_{model}".replace(' ', '_')` — the agent does not choose it. Read it back from the
register response and use it in every subsequent call.

---

## The endpoints

### `POST /agent-device/register`

Register a new device or reconnect an existing one. The entire body is stored as the device's
`info`; `model` / `manufacturer` drive the derived `device_id`.

```jsonc
// request
{ "model": "SM-S134DL", "manufacturer": "samsung", "serial": "R9TT311P25N",
  "capabilities": { "screen_record": true, "android_api": 33 }, "...": "any extra fields kept as info" }

// response
{ "device_id": "samsung_SM-S134DL", "status": "registered", "reconnected": false }
```

Side effects: broadcasts `device_connected`, plus `device_new` (first time) or
`device_reconnected` + a `device.online` notification (was offline). A reconnect fails the previous
connection's in-flight commands with reason `AGENT_RECONNECTED`. **Auth:** open unless
`AGENT_ENROLLMENT_REQUIRED=true` (then the device must already be enrolled and sign the request).

### `POST /agent-device/state`

Full state + metrics push. The reference agent sends this every **2s**. No-op if the `device_id`
isn't already registered.

```jsonc
// request (shape the Kotlin agent sends)
{ "device_id": "samsung_SM-S134DL",
  "metrics": { "cpu_percent": 12.0, "ram_used_mb": 2100, "ram_total_mb": 4096,
               "battery_level": 84, "battery_temperature": 31.0, "is_charging": false,
               "network": { "type": "wifi", "rx_rate": 0, "tx_rate": 0 } },
  "keyboard": { "visible": false, "focused_field_id": null, "...": "..." },
  "window": { "package": "com.android.settings", "activity": "..." },
  "clipboard": "", "notifications": [ ] }

// response
{ "status": "ok" }
```

Side effects: updates the heartbeat clock, broadcasts `device_state`, records a metrics-history
sample, and auto-creates alerts (low battery `<20`, overheating `>45°C`, storage full `<5%` free).
**Auth:** signed if enrolled.

### `POST /agent-device/heartbeat`

Liveness ping. The reference agent sends this every **5s**. No-op if not registered.

```jsonc
// request
{ "device_id": "samsung_SM-S134DL", "timestamp": 1720000000.0 }
// response
{ "status": "ok" }        // broadcasts device_heartbeat
```

**Auth:** signed if enrolled.

### `POST /agent-device/event`

Push an arbitrary device event (appended to a 500-entry ring buffer, broadcasts `device_event`).

```jsonc
// request
{ "device_id": "...", "event": "app_installed", "data": { }, "timestamp": 1720000000.0 }
// response  →  { "status": "ok" }
```

**Auth:** none.

### `GET /agent-device/<device_id>/commands`

The agent **polls** this to drain queued operator commands (up to 10 per poll; drained on read).

```jsonc
// response
{ "commands": [ { "id": "uuid", "command": "reboot", "args": { } } ] }
```

**Auth:** signed if enrolled.

### `POST /agent-device/command-result`

The agent **acks** a command it executed. Unblocks the operator waiting synchronously on
`/dispatch`.

```jsonc
// request
{ "device_id": "...", "command_id": "uuid", "result": { }, "error": null }
// response  →  { "status": "ok" }     (400 if no command_id, 404 {"error":"unknown command"})
```

**Auth:** signed if enrolled.

### `POST /agent-device/<device_id>/dispatch`

The **operator side** — enqueue a command and block for its result. Returns the full command
record; HTTP `200` if it completed, `202` if still pending/timed out.

```jsonc
// request
{ "command": "reboot", "args": { }, "timeout": 30, "source": "dashboard" }
// response  →  a DeviceCommand.to_dict()  (see models below)
```

**Auth:** none (operator-side).

### Read-only status & history

| Method & path | Returns |
| --- | --- |
| `GET /agent-device/status` | `{ "devices": [ <live state> ] }`. Runs the stale-agent reaper first. |
| `GET /agent-device/<id>/metrics` | Latest metrics for one device (`404` if none). |
| `GET /agent-device/<id>/capabilities` | `{ device_id, capabilities: {} }`. |
| `GET /agent-device/<id>/command-history?limit=` | This device's command history. |
| `GET /device-commands?limit=&offset=&status=&device_id=` | Fleet-wide command history. |
| `GET /agent-device/events?limit=` | Recent device events (ring buffer). |

---

## Authentication

There are **two** independent mechanisms; don't confuse them:

- **`X-Agent-Token`** — a static shared token. When `AGENT_TOKENS` is set, `/agent-device/*`
  requires one of the configured tokens in the `X-Agent-Token` header. Empty by default (dev).
- **HMAC request signing** — a per-device secret established through pairing enrollment, used to
  sign each request. This is the strong mechanism (below).

(The dashboard/operator side and droidlink's pytest reporter use a *third* header, `X-API-Key`,
for the general API — not part of the agent contract.)

### HMAC request signing

Once a device is **enrolled** (has a stored secret — see [enrollment](#enrollment--pairing)), the
backend verifies a signature on its requests. An unenrolled device passes through **unless**
`AGENT_ENROLLMENT_REQUIRED=true`, which rejects it with `403 device not enrolled`.

**Headers (all three required when enrolled):**

| Header | Value |
| --- | --- |
| `X-Agent-Timestamp` | Unix seconds as a string (float allowed). |
| `X-Agent-Nonce` | Client-random hex (the reference agent uses 16 random bytes → 32 hex chars). |
| `X-Agent-Signature` | Lowercase hex HMAC-SHA256. |

**The signed string is exactly:**

```
{device_id}:{timestamp}:{nonce}
```

UTF-8, no separators beyond the two colons. Sign it with HMAC-**SHA256** keyed by the device
secret; hex-encode lowercase. Both sides compute it identically and compare with a constant-time
check.

**Verification order and rules** (`agent_device.py`):

1. **Per-IP rate limit** — more than **20 auth failures / 60s** from an IP → `401 rate limited`.
2. **Timestamp window** — `abs(now - timestamp) > AGENT_HMAC_WINDOW` (default **60s**) → rejected.
3. **Signature** — must match (validated against either the active `secret` *or* a
   `secret_pending`, so key rotation has zero downtime).
4. **Nonce replay** — the nonce is remembered for `window × 2` (120s); a repeat within that TTL →
   `401 nonce replay`. The nonce is consumed **only after** the signature verifies, so a forged
   signature can't burn a legitimate nonce.

Failure responses are `401 {"error": "<reason>"}` where reason is one of `missing auth headers`,
`bad timestamp`, `timestamp outside window`, `bad signature`, `nonce replay`, `rate limited`.

> **Reference-agent status:** the Kotlin agent contains the full signing machinery
> (`DeviceKitClient.signed()`), but nothing in the shipped APK ever calls `enroll()` or stores a
> secret, so `isEnrolled()` is always false and its requests currently go out **unsigned**. Pairing
> is wired on the backend and dashboard but not yet in the app. A non-Kotlin agent that implements
> pairing gets signing end-to-end today.

---

## Enrollment / pairing

Enrollment establishes the per-device HMAC secret via a short code, so a device is trusted without
shipping a shared secret. Flow: **enroll (agent) → claim (operator) → poll (agent picks up the
secret, once)**. Codes are 6 characters from an unambiguous alphabet (no `0/O/1/I/L`), TTL **600s**.

### `POST /agent-device/enroll` — agent starts enrollment

```jsonc
// request: device info (model, manufacturer, serial, capabilities, ...)
// response
{ "pairing_id": "uuid", "code": "7KQ4WM", "device_id": "samsung_SM-S134DL", "expires_at": 1720000600.0 }
```

The agent displays `code` to the operator.

### `POST /agent-devices/claim` — operator claims the code

Done from the dashboard (or any operator tool). If `API_KEY` is configured, `passphrase` must equal
it.

```jsonc
// request
{ "code": "7KQ4WM", "passphrase": "<API_KEY if configured>" }
// response
{ "device_id": "samsung_SM-S134DL", "enrolled": true }   // 400: unknown/claimed/expired code
```

This registers/promotes the device, mints an HMAC secret, and stamps the pending row. Broadcasts
`agent_enrolled` + a notification.

### `GET /agent-device/enroll/<pairing_id>` — agent polls for the secret

```jsonc
// while pending  →  { "claimed": false, "code": "7KQ4WM", "expires_at": 1720000600.0 }
// expired/gone   →  { "claimed": false, "expired": true }
// once claimed (returned EXACTLY ONCE, then the row is deleted):
{ "claimed": true, "device_id": "samsung_SM-S134DL", "secret": "<64-hex HMAC secret>" }
```

The agent stores `secret` and signs every subsequent request with it. `GET /agent-devices/pending`
lists unclaimed enrollments for the dashboard (secret never included).

### Key rotation (zero downtime)

Both secrets are accepted while rotating, so there's no window where the agent is locked out:

- `POST /agent-device/<id>/rotate-key` → stages a new secret, returns
  `{ device_id, secret: "<new>", status: "rotating" }`. Old + new both valid.
- `POST /agent-device/<id>/rotate-key/complete` → promotes the pending secret and clears the old
  one → `{ device_id, status: "rotated" }`.

---

## Capabilities

A device advertises capabilities in the `capabilities` field at registration. The backend treats
it as a **map** (`{ "screen_record": true, "android_api": 34, "accessibility": true }`) and exposes
it three ways:

- **FQL fields** — target devices by capability in [Fleet Query Language](../README.md#-fleet-query-language):
  `android_api`, and any `can.<feature>` (e.g. `can.screen_record`, `can.accessibility`,
  `can.root`, `can.input`, `can.notification_listener`). `can.<feature>` resolves against the
  capability map and is **open-ended** — an agent can advertise new keys without a backend change.
- **The `require_capability` step type** — an automation step that gates on a capability:
  `{ capability, mode: "fail" | "warn" }`. `fail` aborts the run when the capability is absent;
  `warn` notes it and continues.
- **Capability-filtered device pickers** — device selectors and bulk actions run FQL, so `can.*`
  filters a fleet down to devices that can do the thing.

> **Wire discrepancy to know:** the current Kotlin agent sends `capabilities` as a **JSON array of
> strings** (`["accessibility", "notification_listener", ...]`), but the backend and FQL expect a
> **map** (`caps.get("screen_record")`). So `can.screen_record = true` filters won't match what the
> current APK sends. A conformant non-Kotlin agent should send a **map**, e.g.
> `{ "screen_record": true, "android_api": 34 }`.

---

## Offline detection

The backend decides a device is offline by a **stale-heartbeat sweep**
(`AgentDeviceMixin.reap_stale_agents`):

- A device `online` with `now - last_heartbeat > AGENT_HEARTBEAT_TIMEOUT` (default **90s**) is
  marked offline.
- The sweep runs as a scheduled job every **30s**, and also inline on every
  `GET /agent-device/status`.
- Freshness is re-checked under a lock, so a heartbeat that lands during the sweep isn't evicted by
  a race. Only a real `online → offline` transition emits `device.offline` (no flapping). On
  eviction the backend fails in-flight commands with `AGENT_OFFLINE`, persists `online=false`, and
  broadcasts `device_disconnected`.

---

## Persistence models

The registry is backed by three SQLAlchemy models (`backend/devicekit/models/`):

**`AgentDevice`** (`agent_devices`): `device_id` (PK) · `serial` · `info` (JSON) · `state` (JSON) ·
`registered_at` · `last_heartbeat` · `online` · `secret` · `secret_pending` · `secret_rotated_at` ·
`capabilities` (JSON) · `last_ip`. `to_dict()` adds derived `enrolled = bool(secret)` and
`rotating_key = bool(secret_pending)`.

**`DeviceCommand`** (`device_commands`): `id` (uuid PK) · `device_id` · `command` · `args` (JSON) ·
`status` (`pending`/`running`/`completed`/`failed`/`timeout`) · `result` (JSON) · `error` ·
`source` · `created_at` · `started_at` · `completed_at`. `to_dict()` adds computed `duration`.

**`PendingAgent`** (`pending_agents`): `id` (uuid PK) · `code` · `device_id` · `info` (JSON) ·
`serial` · `created_at` · `expires_at` · `claimed` · `issued_secret` · `last_ip`. The secret is
omitted from serialization unless explicitly requested.

---

## The reference agent (Kotlin)

For cross-checking a new implementation, here's exactly what `agent-android/` does:

- **Backend URL:** `BuildConfig.DEVICEKIT_SERVER_URL` = `http://127.0.0.1:5050`, overridable in
  Settings. HTTP timeouts: connect 5s, read/write 10s.
- **register** → `POST /agent-device/register` with
  `{ model, manufacturer, brand, sdk, android_version, product, device, serial, agent_version, capabilities }`.
  Retries 3× (5s backoff), falls back to a `/health` ping, else standalone mode.
- **heartbeat** → `POST /agent-device/heartbeat` `{ device_id, timestamp }` every **5000ms**.
- **state** → `POST /agent-device/state` (`DeviceState.toJson()`) every **2000ms**.
- **commands** → polls `GET /agent-device/<id>/commands`, acks via `POST /agent-device/command-result`.
- **signing** → present as code (`X-Agent-Timestamp` / `X-Agent-Nonce` / `X-Agent-Signature`,
  canonical `deviceId:timestamp:nonce`, HMAC-SHA256) but **dormant** until pairing lands in the app
  (see the note under [HMAC signing](#hmac-request-signing)).

---

## Config knobs

Backend env vars that shape this contract (`backend/config.py`):

| Var | Default | Effect |
| --- | --- | --- |
| `API_PORT` | `5050` | Backend port. |
| `AGENT_TOKENS` | *(empty)* | Enables `X-Agent-Token` auth on `/agent-device/*` when set. |
| `AGENT_HEARTBEAT_TIMEOUT` | `90` | Seconds before a silent device is marked offline. |
| `AGENT_HMAC_WINDOW` | `60` | Signature timestamp-skew window (seconds); nonce TTL is 2×. |
| `AGENT_ENROLLMENT_REQUIRED` | `false` | When true, unenrolled devices can't register. |
| `AGENT_COMMAND_TIMEOUT` | `30` | Default synchronous dispatch timeout (seconds). |
| `API_KEY` | *(empty)* | If set, required as the claim passphrase and for operator/API routes. |

For how these devices then surface in the fleet and get controlled, see
[Architecture](ARCHITECTURE.md); for driving them from Python, see [droidlink](droidlink.md).
