# Plan 05 — Jobs, Queue Bus & Scheduler

**Status:** ✅ shipped (2026-07-10)
**Inspired by:** ServerKit's `backend/app/queue_bus/` (SQL-backed SQS-like broker) and
`backend/app/jobs/` (unified Job rows + single consumer + DB-defined schedules)
**Depends on:** 01 (both subsystems are SQLAlchemy tables)

> **Shipped notes.** Ported to `backend/devicekit/queue_bus/` (`models.py` + `QueueBusService`
> façade collapsing ServerKit's broker into DeviceKit's `session_scope` layer) and
> `backend/devicekit/jobs/` (`Job`/`ScheduledJob`, `kind→handler` registry, `JobService` +
> `ScheduledJobService`, `JobConsumer`, `JobScheduler`). `JobsMixin` wires the façade,
> registers core kinds, and starts the consumer + scheduler at server boot (`build_app`);
> `init_jobs` runs at `Client.__init__`. Automation runs now enqueue `automation.run` jobs
> (steps snapshotted in the payload, `max_attempts=1`, per-device serialization lock) — the
> old run daemon thread and the interval schedule-checker daemon are gone; an
> `automation.schedule.tick` `ScheduledJob` (every 30s, DB clock) enqueues due runs.
> Boot reconciliation fails any run left `queued`/`running` by a prior process. Migration
> `b2c3d4e5f6a7` adds the five tables. API: `GET /jobs`, `/jobs/stats`, `/jobs/<id>`,
> `POST /jobs/<id>/retry|cancel`, `/jobs/schedules` (+ run/enable). Frontend: `Jobs.jsx`
> view (recent/failed jobs, schedules, live `job` SSE). SDK: `devicekit_sdk.jobs`
> (enqueue/register/schedule) + extension `jobs`/`schedules` manifest keys with
> pause-on-disable / resume-on-enable / delete-on-uninstall. Tests: `test_queue_bus.py`,
> `test_jobs.py`, `test_scheduler.py`, `test_automation_jobs.py` (81 backend tests green).
>
> **Deviations:** (1) Consumer runs handlers on a bounded `ThreadPoolExecutor` (default 4)
> rather than ServerKit's inline serial loop, so a minutes-long automation can't stall
> schedule ticks; only as many messages as free worker slots are claimed. (2) Visibility
> timeout for the jobs queue is 1h (automations run long; single-process crash = restart,
> handled by reconciliation) and the consumer reaps expired in-flight messages each poll.
> (3) The `AutomationSchedule` table is unchanged (interval-only, frontend untouched); the
> tick handler drives it. Cron cadence is available on system/extension `ScheduledJob` rows
> today; wiring cron into the automation-schedule UI is a follow-up. (4) Session-recording
> capture stays a thread (a tight frame loop, per the plan's judgment call).

## Problem

DeviceKit background work is raw `threading` scattered across mixins: automation run
threads + cancel events (`automation.py` `_active_runs`), an interval-based schedule
checker thread, session-recording capture threads (`streaming.py`), and AI conversation
threads (`prompture_agent.py`). There is no retry, no dead-lettering, no persistence of
pending work (a restart mid-run loses everything silently), no audit trail of what ran,
and every new periodic feature means another hand-rolled daemon thread.

ServerKit had exactly this disease (~8 per-feature daemon threads) and consolidated.

## What ServerKit built (both port nearly verbatim — plain SQLAlchemy)

### Queue Bus (`queue_bus/`)

SQS semantics on a database: `QueueGroup` → `Queue` → `QueueMessage` with status
(pending/in_flight/completed/failed/dead_letter), priority, delayed delivery
(`visible_after`), **visibility timeout** (`invisible_until` — crashed consumers'
messages reappear), `attempts`/`max_attempts` retry, dead-letter on exhaustion.
`QueueBusService` façade: `send/receive/complete/fail/requeue/ensure_queue`. No Redis,
no RabbitMQ — perfect for a self-hosted SQLite deployment.

### Unified Jobs (`jobs/`)

- `Job` row: `kind` → handler, payload, status, result, timestamps. A thin pointer
  `{job_id}` rides the queue; the **single `JobConsumer` daemon thread** claims
  messages, looks up the handler in an in-memory `kind → handler` registry, and maps
  the outcome back onto the Job row (retry/dead-letter included).
- `ScheduledJob` row: cadence as data (cron or `interval_seconds`) + `next_run_at` +
  `enabled`. A `JobScheduler` ticks every 15s and enqueues due jobs. Two critical
  details: `ensure()` is **idempotent and preserves `next_run_at`/`enabled` across
  restarts** (redeploys don't reset clocks), and schedules are just rows — pausing a
  feature's periodic work is an UPDATE, not a code change.
- Retention: `prune_terminal` batches, keeping failed jobs 3× longer than succeeded.

## Design for DeviceKit

1. Port `queue_bus/` and `jobs/` as `backend/devicekit/queue_bus/` and
   `backend/devicekit/jobs/` (strip ServerKit-specific consumers). Wire the consumer +
   scheduler startup into `Client` init / `api_app()` boot.
2. Register initial job kinds:
   - `automation.run` — automation execution moves from ad-hoc threads to jobs.
     Run cancellation maps to job cancel; the run thread's cancel-event pattern stays
     inside the handler. **Concurrency:** allow N parallel automation jobs (per-device
     serialization comes free if the handler acquires the existing `device_lock`).
   - `automation.schedule.tick` — replaces the schedule-checker thread with
     `ScheduledJob` rows (one per automation schedule; cron support is an upgrade over
     today's interval-only checker).
   - `bundle.retention.prune`, `session.recording.capture` (or keep capture as a
     thread — it's a tight frame loop, judgment call), `metrics.collect` (plan 08),
     `notification.deliver` (plan 06).
3. Extension job kinds (plan 03): manifest `jobs`/`schedules` register into the same
   registry; disable pauses that extension's schedules (port `pause_jobs/resume_jobs`).
4. API + UI: `GET /jobs`, `GET /jobs/<id>`, `POST /jobs/<id>/retry|cancel`. A simple
   Jobs view (or a panel in an existing view) listing recent/failed jobs — ServerKit
   proves how much debugging pain this removes.
5. Keep SSE events flowing: job status transitions broadcast on the existing
   `subscribeToEvents` channel so views update live.

## What NOT to move

SSE client queues, MJPEG proxy loops, and live viewer counting stay as they are —
they're connection-bound, not work-bound. The AI conversation threads can stay
initially; migrate later if they need retry/audit.

## Risks / notes

- SQLite write contention: the queue polls with short transactions; ServerKit runs
  this shape in production on SQLite. Keep poll interval ≥ 1s and batch claims.
- Single-process assumption holds (consumer + scheduler are in-process daemons) —
  consistent with DeviceKit today; a future multi-worker story swaps the broker, not
  the API.
- Automation runs currently stream step-by-step progress via SSE from inside the
  thread; the job handler keeps doing exactly that.

## Definition of done

No feature-owned daemon threads except stream capture; automations queue, run, retry,
and survive a mid-run backend restart with a coherent status (failed with reason, not
vanished); schedules live in the DB and persist their clocks across restarts; a failed
run is inspectable in a jobs list with its error.

✅ **All met.** The run + schedule-checker daemons are retired (only stream capture keeps a
thread); `execute_automation` enqueues and the run completes/retries on the job system;
`reconcile_interrupted_runs` turns a mid-run restart into `failed` with a reason (verified by
`test_run_survives_restart_as_failed`); `ScheduledJobService.ensure` preserves `next_run_at`
across a restart (`test_ensure_is_idempotent_and_preserves_clock`); and failed jobs/runs are
inspectable via `GET /jobs` and the Jobs view with their error. Verified live: an automation
run went `queued → succeeded` through the consumer and the `automation.schedule.tick`
schedule fired on its own.
