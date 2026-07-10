# Plan 08 — Metrics History & Fleet Monitoring

**Status:** proposed
**Inspired by:** ServerKit's `backend/app/services/metrics_history_service.py`
(rollups + retention tiers), `metric_alert.py`, and `frontend/src/pages/FleetMonitor.jsx`
**Depends on:** 01 (metrics tables), 05 (collection as a scheduled job)
**Aligns with:** DeviceKit ROADMAP Phase 22 (Predictive Device Health) — this plan is
its data foundation

## Problem

DeviceKit devices report rich state (battery, storage, thermals, network) via agent
heartbeats, but only the **latest snapshot** is kept, in memory. `DeviceCompare` charts
whatever it can poll live. Phase 22's predictive features (battery degradation, storage
fill-rate projection, thermal throttling detection) are impossible without history.

## What ServerKit does

- A collector samples metrics every 60s into a raw table.
- **Rollup pipeline:** raw minute rows aggregate into hourly rows, hourly into daily —
  each tier with its own retention (raw 24h, hourly 7d, daily 30d). Old tiers prune on
  schedule. Storage stays bounded regardless of fleet size × uptime.
- Period query API: `?period=1h|24h|7d|30d` picks the right tier transparently.
- `metric_alert.py`: threshold rules on metrics feed the notification bus.
- Frontend `FleetMonitor.jsx`: multi-server recharts line/area charts with a metric
  selector and categorical series colors; design-system `Sparkline`/`Gauge`/
  `MetricCard` primitives for inline trends.

## Design for DeviceKit

### Backend

1. `MetricsHistoryMixin` (ROADMAP Phase 22 already names it) + tables (plan 01):
   `device_metrics_raw`, `device_metrics_hourly`, `device_metrics_daily`.
   Columns: device_id, ts, battery_pct, battery_temp, cpu_load, mem_free,
   storage_free, network_type, screen_on — plus a JSON column for extension-reported
   metrics (plan 03 extensions can contribute samples).
2. Collection: agent heartbeats **already carry state** — persist a sample on
   heartbeat ingest (cheap, no new polling), plus a `metrics.rollup` and
   `metrics.prune` `ScheduledJob` (plan 05) for aggregation/retention.
3. Endpoints: `GET /devices/<id>/metrics?metric=battery_pct&period=7d`,
   `GET /fleet/metrics?metric=...&devices=...` (multi-device aligned series for
   comparison charts).
4. Threshold alerts: simple rules table (`metric, op, value, event_key`) evaluated at
   ingest, emitting through plan 06 (`device.battery.critical`, `device.storage.low`).
5. Phase 22 predictive layer (fill-rate projection, degradation slopes, composite
   health score) builds on these tables later — out of scope here, but the schema
   should keep enough resolution for it (hence 24h of raw minutes).

### Frontend

1. `FleetMonitor`-style view (or a Dashboard widget, plan 11): metric selector +
   multi-device line chart over selectable periods.
2. Sparklines on device cards (`Dashboard.jsx`) and in `NodeDetail` — a tiny inline
   SVG component like ServerKit's `ds/Sparkline.jsx` is ~50 lines and instantly makes
   the fleet feel alive.
3. `DeviceCompare.jsx` upgrades from live-poll-only to historical series.

### FQL integration

Expose derived fields through the existing `SUPPORTED_FIELDS` registry:
`battery.trend_24h < 0`, `storage.free_gb`, `metrics.cpu_load_1h_avg > 2.0` — making
history queryable is where this plan compounds with DeviceKit's differentiators.

## Phases

1. Tables + heartbeat-ingest sampling + period query endpoint.
2. Rollup + prune scheduled jobs; sparklines in Dashboard/NodeDetail.
3. Fleet monitor chart view + DeviceCompare historical mode.
4. Threshold alert rules → notification bus; FQL derived fields.

## Definition of done

A device online for a week shows a 7-day battery/storage chart from bounded storage;
"battery below 20%" produces a notification; an FQL query can select devices by a
metric trend; nothing degrades when 50 devices heartbeat concurrently.
