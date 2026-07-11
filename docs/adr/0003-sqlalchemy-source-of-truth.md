# ADR 0003 — SQLAlchemy is the single source of truth

- **Status:** Accepted
- **Recorded in:** [plan 01 — persistence layer](../plans/01-persistence-layer.md).

## Context

Everything durable in DeviceKit used to live in **process memory** — automations, runs, fleet groups,
saved FQL queries, visual baselines, debug-bundle metadata, stream sessions, the agent-device
registry, AI conversations — all class-level lists and dicts on mixins, **lost on every backend
restart**. `DynamoDBMixin` / `AwsStorageMixin` existed but nothing called them, and the ROADMAP had
explicitly deferred "persistence across restarts."

## Decision

Make **SQLAlchemy 2.0 models the single source of truth**, with **SQLite (WAL) as the default
embedded store**, configured by `DEVICEKIT_DATABASE_URL` (Postgres-ready). Alembic migrations run at
boot via `migrate.check_and_prepare()`, owned by a `PersistenceMixin` registered **first** in
`client.py`.

## Rationale

SQLite is zero-infrastructure, matching DeviceKit's docker-compose / self-hoster / CI-lab shipping
model, while a `DATABASE_URL` env var leaves Postgres open for scale. Decisively, the borrowed
ServerKit subsystems (extensions, jobs/queue, notification bus, metrics rollups) are all **written
against SQLAlchemy** — with SQLite they lift nearly verbatim, whereas a DynamoDB port would be a
rewrite.

## Consequences

- A restart loses no automations, runs, groups, queries, baselines, bundles, or registered agent
  devices.
- **Response envelopes and field conventions are unchanged** (`{'resource': [...], 'count': N}`,
  `uuid4` ids, `time.time()` timestamps) — the frontend and `api.js` needed **zero edits**.
- Data access uses short-lived per-operation sessions (`db.session_scope()`), not one long-lived
  session.
- The **single-process constraint remains**: genuinely ephemeral state (SSE client queues, MJPEG
  viewer counts, in-flight run threads, the agent event ring buffer, share tokens) is intentionally
  *not* persisted.

## Alternatives considered

- **Keep in-memory state** — that was the defect being fixed.
- **The existing DynamoDB/S3 mixins as the primary store** — rejected because the borrowed
  subsystems assume SQLAlchemy; DynamoDB/S3 remain only as an optional blob/archive backend.
