# Plan 01 — Persistence Layer

**Status:** ✅ shipped
**Inspired by:** ServerKit's SQLAlchemy model layer (`backend/app/models/`, ~90 models, SQLite default / Postgres optional)
**Depends on:** nothing — this is the foundation for plans 03, 05, 06, 07, 08

> **Shipped notes.** SQLAlchemy 2.0 + SQLite (WAL) is the default store, configured by
> `DEVICEKIT_DATABASE_URL` (Postgres-ready). `db.py` hands out short-lived `session_scope()`
> units of work; `PersistenceMixin` (registered first in `client.py`) brings up the engine
> and runs `migrate.check_and_prepare()` at boot — `create_all + stamp head` on a fresh DB,
> `alembic upgrade head` thereafter. All response envelopes and field conventions are
> unchanged, so the frontend and `api.js` needed zero edits. Verified end-to-end: a real
> backend restart preserved an automation, a device group, a saved query, and a registered
> agent device (see the migration table below). A pytest suite under `backend/tests/`
> proves restart-survival for every migrated store (14 tests).
>
> **Deviations:** (1) automations + schedules + runs shipped together (one file); (2)
> `RecordedFrame` was folded into on-disk frames + `StreamSession.frame_count` rather than a
> row-per-frame (avoids high write volume; frames live under `output/recordings/<id>/`); (3)
> debug-bundle ZIPs and recording frames are stored on disk, not in the DB; (4) share tokens
> and the agent-device event ring buffer stay in memory on purpose (short-lived / ephemeral).

## Problem

Everything in DeviceKit is process-memory. Automations, runs, fleet groups, saved FQL
queries, visual-regression baselines, debug bundles, stream sessions, agent-device
state, and AI conversations all live in class-level lists/dicts inside mixins
(`backend/devicekit/mixins/*.py`) and are **lost on every backend restart**. The
`DynamoDBMixin`/`AWSStorageMixin` exist (`dynamodb.py`, `aws_storage.py`) but no
feature calls them. The ROADMAP itself defers "persistence across backend restarts."

## What ServerKit does

- SQLAlchemy models are the single source of truth; SQLite by default (zero infra,
  perfect for self-hosted docker-compose), Postgres for scale.
- `db.create_all()` at boot plus Alembic for migrations
  (`backend/app/services/migration_service.py` runs `check_and_prepare` before anything
  else loads).
- Services read/write rows; in-memory state is reserved for genuinely ephemeral things
  (live socket registries, in-flight commands).
- Encrypted-at-rest columns for secrets (`backend/app/utils/crypto.py`) with an
  idempotent legacy migration at startup.

## Design for DeviceKit

### Storage choice

Recommend **SQLite via SQLAlchemy** as the default embedded store:

- DeviceKit ships via docker-compose and targets self-hosters/CI labs — zero-infra
  SQLite matches that, and a `DATABASE_URL` env var leaves Postgres open.
- Plans 03/05/06/08 borrow ServerKit subsystems (queue bus, jobs, extension rows,
  metrics rollups) that are **written against SQLAlchemy** — with SQLite they can be
  lifted nearly verbatim; a DynamoDB port would be a rewrite.
- The existing DynamoDB/S3 mixins can remain as an optional blob/archive backend
  (debug-bundle ZIPs, recording frames belong in object storage anyway) or be retired.
  Decide during implementation; don't block on it.

### Shape

1. New `backend/devicekit/db.py`: engine + session factory + `Base`, configured from
   `config.py` (`DEVICEKIT_DATABASE_URL`, default `sqlite:///devicekit.db`).
2. New `backend/devicekit/models/` package — one module per domain, mirroring the
   mixins that own the data today:
   - `automation.py` — `Automation`, `AutomationRun`, `AutomationSchedule`
   - `fleet.py` — `DeviceGroup`, `DeviceTag`, `SavedQuery`
   - `baseline.py` — `VisualBaseline`
   - `bundle.py` — `DebugBundle` (metadata; ZIP bytes → disk or S3)
   - `session.py` — `StreamSession`, `RecordedFrame` (metadata; frames on disk)
   - `agent_device.py` — `AgentDevice` (registered devices, last state, serial index)
   - later: `installed_extension.py` (plan 03), `job.py`/`queue.py` (plan 05),
     `notification.py` (plan 06), `metrics.py` (plan 08)
3. A `PersistenceMixin` (following the `new-mixin` conventions) that owns the session
   lifecycle and is registered in `client.py` before every data-owning mixin.
4. Migrate mixins one at a time: keep the mixin's public method signatures identical so
   `api_app.py` routes don't change; swap the class-level list for queries. The
   existing in-memory dict shape becomes `to_dict()` on the model.
5. Alembic from day one (ServerKit's boot-time `check_and_prepare` pattern), so later
   plans can add tables safely.

### Migration order (lowest risk first)

1. Saved FQL queries + fleet groups/tags (small, low-traffic)
2. Automations + schedules (highest user pain when lost)
3. Automation runs + step results (append-heavy; verify write volume is fine)
4. Visual baselines, debug-bundle metadata, stream-session metadata
5. Agent-device registry (`_agent_device_states` in `api_app.py` — coordinate with plan 07)

Ephemeral state stays in memory on purpose: SSE client queues, MJPEG viewer counts,
in-flight run threads, live agent sockets.

## Risks / notes

- **Single-worker constraint:** ServerKit runs one Gunicorn worker because live
  registries are in-memory. DeviceKit has the same shape (SSE queues, run threads).
  Persisting durable state doesn't remove that constraint — document it, and don't
  pretend multi-worker works until live state moves to a backplane.
- Thread-safety: run threads and the schedule checker will now write rows —
  use short-lived sessions per operation, not one long-lived session.
- Keep the `{'resource': [...], 'count': N}` response envelope and uuid4/`time.time()`
  field conventions so the frontend and `api.js` are untouched.

## Definition of done

Restarting the backend loses no automations, runs, groups, saved queries, baselines,
bundles, or registered agent devices. ✅ Met — verified by the `backend/tests/` suite and a
live restart E2E.

## Which mixin persists where

| Mixin (`backend/devicekit/mixins/`) | Table(s) (`models/`) | Notes |
| --- | --- | --- |
| `fleet_query.py` (`FleetQueryMixin`) | `saved_queries` | Preset queries stay code-level constants. |
| `fleet.py` (`FleetMixin`) | `device_groups`, `device_tags` | Tags = one JSON row per device. |
| `automation.py` (`AutomationMixin`) | `automations`, `automation_schedules`, `automation_runs` | Runs upserted via `_save_run` per step; live cancel handles (`_active_runs`) stay in memory; scheduler reads due rows each tick; `resume_schedules()` restarts the checker at boot. |
| `visual_regression.py` (`VisualRegressionMixin`) | `visual_baselines` | Screenshot bytes in a BLOB column; `to_dict(include_image=)` splits API metadata from internal compare callers. |
| `debug_bundle.py` (`DebugBundleMixin`) | `debug_bundles` | Metadata in DB; ZIP payload on disk (`output/debug_bundles/<id>.zip`); share tokens in memory. |
| `streaming.py` (`StreamingMixin`) | `stream_sessions` | Session metadata + events persisted; frames on disk (`output/recordings/<id>/`); viewer counts / capture threads stay in memory. |
| `agent_device.py` (`AgentDeviceMixin`) + `api_app.py` closure | `agent_devices` | Closure cache hydrates from rows at boot and writes through; event ring buffer ephemeral. Coordinates with plan 07. |

**Ephemeral by design (never persisted):** SSE client queues, MJPEG viewer counts,
in-flight run threads / cancel events, live capture threads, the agent-device event ring
buffer, and bundle share tokens.

**Out of scope for this plan:** alerts, activities, pipeline builds, and `_config` remain
in-memory (not in the DoD list; revisit with their own plans).
