# Plan 24 — Fleet Health, Sweeps & Auto-Remediation

**Status:** proposed
**Inspired by:** ServerKit runs a large fleet on a **single-worker control plane by discipline, not
infrastructure** — and that reframes the "fleet scale" idea floated earlier. `fleet_sweep.py` fans a
per-agent probe across the fleet with a **bounded worker pool (≤4), a per-agent timeout, and a hard
wall-clock budget**; a hung agent yields a `timeout` row, never a stalled control plane
(`docs/FLEET_CONTRACT.md` lists gateway horizontal-scaling as *explicitly out of scope*). On top of
the sweep sit four cooperating services: `doctor_service.py` (uniform check rows
`{key, title, status, detail, repairable, repair_ref}`, every probe best-effort), `fleet_doctor_service.py`
(the doctor fanned across agents, one `FleetDoctorResult` per `(device_id, check_key)`, `repairable`
only if the agent advertises the capability), `fleet_repair_service.py` (remediation is a
**data-driven allowlist** `kind → {command, required capability, permitted targets, permission
scope}`, refused server-side if off-list, **every attempt audited**), and `drift_service.py`. Plus
`fleet_monitor_service.detect_anomalies` (per-device 7-day **z-score**) and `forecast_capacity`
(**linear-regression** days-to-full/dead) — the exact predictive layer Phase 22 still needs.
**Depends on:** 05/25 (**sweeps run in job handlers only, never on a request thread**), 07/29
(capability map — repairs gate on capabilities), 08 (metrics history feeds z-score + forecast), 06
(edge-triggered alerts on the bus). Soft: 23 (shares the drift primitive).

## The reframe: you probably don't need multi-node

ServerKit's answer to "big fleet, one Flask process, in-memory registry, no broker" is **not**
Redis/Postgres pub-sub or sharding — it deliberately declined all of that. The portable model is
architectural: **bounded off-thread sweeps + capability-gating + row-keyed results**. Adopt that
before reaching for infrastructure. If DeviceKit ever truly needs multi-node SSE/agent fan-out,
ServerKit offers no prior art — that's greenfield (see plan 25's non-goals).

## The questions this plan answers

- **"How do I check or act across the whole fleet without one dead device hanging everything?"**
  `fleet_sweep`: bounded pool, per-device timeout, hard budget; a hung device is a `timeout` row.
- **"Can DeviceKit diagnose and fix unhealthy devices?"** Yes, but with discipline copied verbatim:
  **detection and remediation are decoupled; remediation is allowlisted, capability-gated, audited,
  and operator-triggered by default** — automatic repair is the exception, not the rule. Start with
  a 1–2 action allowlist like ServerKit did.
- **"Can I predict failures instead of just reacting?"** Yes — z-score anomaly ("this device is
  abnormal vs its own baseline") + linear-regression capacity forecast ("storage full / battery
  degraded in ~N days"). This finishes the half-built Phase 22.

## Part 1 — `fleet_sweep`: the bounded fan-out primitive

- Off-thread fan-out with a bounded pool + per-device timeout + wall-clock budget; results are
  **rows keyed `(device_id, check_key)`, not a blob**. The executor shuts down `wait=False` so one
  slow device never blocks the return.
- The six FLEET_CONTRACT rules as DeviceKit's fleet-op checklist: address by `device_id` always;
  **capability-gate, never error** (unknown-capability device → `unsupported`, not a crash — old
  agents work forever); per-device rows not blobs; **sweeps in job handlers only**; compose from
  commands every agent already speaks before adding new ones; remote mutations allowlisted +
  audited.

## Part 2 — Device doctor

- A health sweep producing uniform rows (agent unreachable, app crashed, storage low,
  offline-too-long, config drifted, battery critical). Every probe **best-effort** — a failure is a
  `warn` row, never an exception. `repairable` set only when the device advertises the needed
  capability.

## Part 3 — Fleet repair (allowlisted, audited, operator-triggered)

- Remediation is a **data-driven allowlist**: `kind → {agent command, required capability, permitted
  targets, permission scope}`. Anything off-list is refused *before* dispatch; capability gaps
  refuse cleanly; **every attempt is audited** (plan 20 `AuditService`).
- v1 allowlist stays tiny (like ServerKit's restart-nginx/docker only): e.g. `restart_app`,
  `repush_config`. Batch repair runs **only for the items an operator explicitly selected**.
- Reboot / re-enroll / factory-reset are higher-danger tiers gated to platform-admin (plan 20).

## Part 4 — Predictive health (finishes Phase 22)

- **z-score** over rolling per-device metric history (mean/stddev, flag |z|>2.5, needs ≥10–20
  samples) → "abnormal vs its own baseline." Pure Python over metrics you already store (plan 08).
- **linear-regression** capacity forecast → days-to-storage-full and battery-degradation trend.
- Threshold engine with per-device-override→global resolution + duration window + active-alert
  de-dup. `GET /fleet/health/predictions` lists devices with active predictions + ETA. Dashboard
  "Predictions" card ("Device X: storage full in ~3 days").
- Note: ServerKit's version is naive (no seasonality, fixed 2.5σ) — good enough to ship, worth
  hardening later.

## Part 5 — Edge-triggered alerts

- Fire **once** on healthy→failed and **once** on recovery (failed→success), previous state
  remembered per check (`backup_alert_service.py`'s pattern). Kills the notification-bus fatigue that
  naive per-sweep re-firing causes.

## Part 6 (optional) — Fleet status page

- Public page: fleet uptime % over 24h/7d/30d, current incidents **auto-opened** on major-outage
  and **auto-resolved** on recovery (resolve on the leaving-edge so a recovery passing through a
  "degraded" poll doesn't get stuck open). The public payload **strips internal probe config**.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | `fleet_sweep` bounded off-thread fan-out (per-device timeout, budget, `(device_id, check_key)` rows) + the six-rule checklist | fleet-wide ops that never stall |
| 2 | device doctor: uniform best-effort check rows, `repairable` gated on capability | diagnosis, decoupled from action |
| 3 | fleet repair: data-driven allowlist, capability-gated, audited, operator-triggered | safe auto-remediation |
| 4 | predictive health: z-score anomaly + regression forecast + `/fleet/health/predictions` + Predictions card (finishes Phase 22) | failures predicted, not just reacted to |
| 5 | edge-triggered health alerts | no alert fatigue |
| 6 | (optional) fleet status page (uptime %, auto-incidents, stripped public payload) | external trust surface |

Phase 1 is the foundation (needs plan 05 jobs). 2→3 sequential on 1. Phase 4 is independent of 2/3
(needs plan 08). 5 rides 2. 6 rides 2.

## Decisions to make while executing (log, don't stop)

- **Repair automation default:** operator-triggered (recommended, ServerKit's stance) vs auto. Keep
  auto opt-in per repair kind, audited, with a kill-switch.
- **Anomaly method:** z-score (recommended, ships today) vs a heavier model. Ship z-score; harden
  later.
- **Sweep cadence:** scheduled job interval per check class (health more often than forecast). Make
  it a `ScheduledJob` (plan 05), tunable.

## Out of scope

- **Multi-node / horizontally-scaled control plane.** ServerKit explicitly declined it; adopt
  bounded sweeps instead. If genuinely needed later, it's a separate greenfield effort.
- **ML-grade forecasting** (seasonality, per-model battery curves). Linear regression + z-score is
  the v1; note the ceiling.
- **Streaming over the sweep transport.** Sweeps are request/response batches; live streaming is
  plan 18-era work (Phase 18).

## ServerKit source map (for implementers)

- Sweep primitive + contract: `backend/app/services/fleet_sweep.py`, `docs/FLEET_CONTRACT.md`
- Doctor / fleet-doctor / repair / drift: `backend/app/services/doctor_service.py`,
  `fleet_doctor_service.py`, `fleet_repair_service.py`, `drift_service.py`
- Predictive: `backend/app/services/fleet_monitor_service.py` (`detect_anomalies` z-score,
  `forecast_capacity` regression, `check_fleet_thresholds`)
- Edge alerts: `backend/app/services/backup_alert_service.py` (state-transition pattern)
- Status page: `backend/app/services/status_page_service.py`, `uptime_service.py`
- Agent trust boundary the probes respect: `docs/AGENT_DOCTOR_PROBE_SPEC.md`,
  `docs/AGENT_SURVEY_SPEC.md`
- **Two disciplines to internalize:** *best-effort everywhere* (probes/alerts/audit swallow their
  own exceptions so they never break the operation they observe), and *decouple detect from act;
  make acting allowlisted + capability-gated + audited + operator-triggered by default*.
