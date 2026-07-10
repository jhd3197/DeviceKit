# Plan 01 — Persistence Layer

**Status:** proposed
**Inspired by:** ServerKit's SQLAlchemy model layer (`backend/app/models/`, ~90 models, SQLite default / Postgres optional)
**Depends on:** nothing — this is the foundation for plans 03, 05, 06, 07, 08

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
bundles, or registered agent devices. `docs/plans/` gains a short "which mixin persists
where" table in this file as migration completes.
