# Plan 07 — Agent Security & Fleet Registry Hardening

**Status:** 🚧 in progress (phase 1 ✅)
**Inspired by:** ServerKit's `backend/app/services/agent_registry.py` (1,035 lines — the
richest single code reference), `agent_gateway.py`, `pairing_service.py`,
`docs/FLEET_CONTRACT.md`
**Depends on:** 01 (device rows, command audit rows)

## Problem

DeviceKit's on-device agent (Kotlin APK) registers over plain HTTP endpoints
(`/agent-device/register|state|heartbeat|event`) whose state lives in dicts inside
`api_app.py`. The ROADMAP itself defers "agent-side HTTPS/token." Concretely missing:
real agent authentication, replay protection, a principled offline detector, a
persisted command/audit trail, capability-based device targeting, and a humane
enrollment flow. ServerKit solved each of these for its Go server agents, and the
patterns map almost 1:1 to Android device agents.

## Patterns to port

### 1. HMAC agent auth with replay protection

ServerKit agents sign `agent_id:timestamp:nonce` with a per-agent secret
(HMAC-SHA256); the panel verifies the signature **before** consuming the nonce
(documented subtle fix), rejects timestamps outside a 60s window, tracks nonces to
block replays, rate-limits auth per IP, and records anomalies (new IP, repeated
failures). Per-agent credentials are issued at enrollment; the `Server` model carries
full **key-rotation** columns (`api_key_pending_*`, `start_key_rotation()` /
`complete_key_rotation()`) so keys rotate without downtime.

**DeviceKit:** issue a per-device secret at enrollment; the Kotlin agent signs each
request (or the initial session handshake) the same way. This closes the
ROADMAP-deferred auth gap with a proven design.

### 2. Enrollment / pairing (RustDesk-style)

ServerKit's `pairing_service.py`: the agent displays/uses a rotating 6-character code;
the operator confirms with a passphrase; an enroll→poll→claim flow mints and encrypts
credentials, with a `PendingAgent` row until claimed.

**DeviceKit:** the agent APK shows a pairing code on screen; the operator types it into
the dashboard (or scans adb-side). Beats today's open `/agent-device/register`, and
demos beautifully.

### 3. Registry with reconnection correctness

`ConnectedAgent` dataclasses in a lock-guarded in-memory registry + a background
**heartbeat reaper** (90s timeout) with two race fixes worth stealing outright:

- The reaper **re-validates connection identity under lock before evicting**, so a
  fresh reconnect isn't clobbered by a stale timeout.
- A reconnect **fails the old connection's in-flight commands with
  `AGENT_RECONNECTED`** instead of letting callers hang.

**DeviceKit:** the live registry becomes a proper mixin/service (out of `api_app.py`
closures — coordinates with plan 02), backed by an `AgentDevice` row (plan 01) for
durable identity/last-seen. The reaper emits `device.offline` through plan 06.

### 4. Synchronous command dispatch over async transport

`send_command()` emits to the agent and blocks the calling request thread on a
`queue.Queue.get(timeout)`; the agent's `command_result` puts the response on that
queue. Every command is persisted as a row (pending→running→completed/failed) — a
complete device-action **audit trail** for free.

**DeviceKit:** wrap agent HTTP/push dispatch in the same primitive with per-command
timeouts, and persist `DeviceCommand` rows. This also gives the UI a "device action
history" panel with zero extra bookkeeping.

### 5. Capability advertisement → capability-driven targeting

ServerKit agents report a capability map on connect (`cached_capabilities` on the
model); `GET /fleet/targets?feature=cron` returns only agents that can do it, and
workflow nodes include `capability_gate` / `runtime_gate` (version-compare) steps.

**DeviceKit:** agents already report metadata; formalize it — `{screen_record: true,
accessibility: true, root: false, android_api: 34}`. Then:
- Fleet FQL gains capability fields (`can.screen_record = true`) via the existing
  `SUPPORTED_FIELDS` registry.
- Automations gain a `require_capability` step type (in `STEP_TYPES`) so a flow
  fails fast — or skips a device — instead of dying mid-run.
- Device pickers filter to capable devices ("only devices that can screen-record").

### 6. Dual transport (nice-to-have)

ServerKit supports WS + HTTP long-poll against one registry. DeviceKit's agents are
HTTP-polling today; the registry abstraction (`transport` field, `drain_outbound`)
leaves room to add a push channel later without reworking callers.

## Phases

1. ✅ Registry extraction to a mixin + `AgentDevice`/`DeviceCommand` persistence +
   heartbeat reaper with the two race fixes.
   - `AgentDeviceMixin` hardened with an `RLock`-guarded registry, reconnect-aware
     `register_agent_device` (fails old in-flight commands with `AGENT_RECONNECTED`),
     `reap_stale_agents` (offline exactly once; freshness re-validated under lock so a
     quick reconnect never flaps), and synchronous `send_command`-style dispatch over the
     poll transport backed by a `DeviceCommand` audit row (pending→running→completed/
     failed/timeout). Reaper runs as an `agent.heartbeat.reap` scheduled job (30s).
     New endpoints: `/agent-device/command-result`, `/agent-device/<id>/dispatch`,
     `/agent-device/<id>/command-history`, `/device-commands`. Migration
     `a71c07a10001` (device_commands). Tests: `tests/test_agent_registry.py` (6).
2. HMAC auth + nonce/timestamp guard + per-device secrets (agent APK update — token
   storage + signing in the Kotlin `AgentHttpServer` client path).
3. Pairing flow (backend + APK pairing screen + dashboard claim UI).
4. Capability map formalization + FQL fields + `require_capability` step type +
   key rotation.

> **Assumption (logged):** auth stays *opt-in* for dev/back-compat. The full HMAC guard
> (`verify_agent_request`) + per-device secrets ship in phase 1's mixin but are only
> enforced for enrolled devices, or globally when `AGENT_ENROLLMENT_REQUIRED=true`. This
> satisfies the "unenrolled agent cannot register" DoD without breaking the auth-disabled
> dev flow or the current APK. The reaper offline window moved 15s→90s (config
> `AGENT_HEARTBEAT_TIMEOUT`), matching ServerKit.

## Definition of done

An unenrolled agent cannot register; a replayed request is rejected; killing an agent
marks the device offline exactly once (no flap on quick reconnect) and notifies; every
device command is queryable history; an automation can gate on device capability.
