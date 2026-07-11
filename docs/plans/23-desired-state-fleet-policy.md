# Plan 23 — Desired-State Fleet Policy (`devicekit.yaml`)

**Status:** proposed
**Inspired by:** ServerKit's `serverkit.yaml` is a full desired-state reconcile loop, framed
exactly right in `docs/SERVERKIT_YAML.md`: *"live panel state is the state; the manifest is the
desired state."* The pipeline is worth porting almost 1:1: **spec**
(`manifest_spec_service.py` + `serverkit-yaml.schema.json`, JSON-Schema validated, normalized) →
**persist** (`manifest_persistence_service.py`, raw text + normalized JSON + **sha256 hash** +
status `pending | applied | drifted | error`) → **plan** (`manifest_apply_service.plan`, a pure
dry-run diff → **ordered** action steps via a `_STEP_ORDER` weight map, emitting advisory `issues`
*and* hard **`blockers`** — the "honesty rule": apply *refuses* rather than half-deploy) →
**apply** (inside a `DeploymentJob`, before/after snapshots, per-step ok/error/skipped, idempotent —
an unchanged hash short-circuits) → **reconcile** (`manifest_sync_service.py` re-reads on every
push; `autoDeploy:true` auto-applies, the rest flip to `pending` with a notification) → **scaffold**
(`manifest_scaffold_service.py` renders YAML *from* live state; secrets never in YAML — `fromSecret`
refs or `generate:true` → store in vault). For a device fleet this is **MDM-grade policy
enforcement**.
**Depends on:** 18 (app-driver provisioning + `device_requirements` — the "desired app at pinned
version" primitive already exists), 05/25 (jobs — apply runs as a job), 20 (secrets vault —
`fromSecret` refs), 24 (drift detection shares the drift primitive). Soft: 15 (automation templates
as declarable state), 22 (declared automations are graph automations).

## The questions this plan answers

- **"Can I declare what a device (or group) *should* look like and have DeviceKit make it so?"**
  Yes — a `devicekit.yaml` declares, per device or FQL-selected group, the desired installed apps
  (package + pinned version, riding plan 18), enabled automations/schedules, config/settings, and
  extension set. DeviceKit plans the diff and applies it.
- **"What if applying would break something?"** The plan surfaces hard **blockers** ("APK not
  supplied", "device offline", "app version has no adapter", "extension dependency missing") and
  **refuses to apply** rather than half-configuring a device — the honesty rule.
- **"How do I know a device drifted from policy?"** Periodic diff of actual-vs-desired flips the
  policy to `drifted`, alerts (edge-triggered, plan 24), and offers reconcile.
- **"I already have a fleet — do I hand-write YAML for all of it?"** No — scaffold renders a policy
  from a live device's current state; adopt, then edit.

## Part 1 — Schema + validator

- `devicekit.yaml` (`version: 1`), JSON-Schema (Draft 7) validated, normalized to a stable internal
  dict (camelCase canonical, snake_case aliases accepted). Declares: `target` (device id / group /
  FQL), `apps` (package + version + provision source, plan 18), `automations` (enable + schedule),
  `settings`, `extensions`.

## Part 2 — Persist as a `FleetPolicy`

- One row per policy: raw text + normalized JSON + **sha256 hash** + provenance (who/when, optional
  git repo/ref/commit) + status `pending | applied | drifted | error`, scoped to a device/group
  (and to a workspace, plan 20).

## Part 3 — Plan (dry-run diff → ordered steps + blockers)

- Pure diff desired-vs-live per device → **ordered** action steps via a weight map
  (`provision_app → install → configure_setting → enable_automation → attach_extension`).
- Advisory `issues` vs hard `blockers`. **Blockers refuse the apply** (no `--force` half-deploy):
  APK unsupplied, device offline/unreachable, version-out-of-adapter-range (plan 18), missing
  required extension (plan 17).

## Part 4 — Apply (as a job, idempotent, snapshotted)

- Execute steps through existing imperative seams (plan 18 `provision`, plan 15 step types, settings
  writes) inside a job, with **before/after snapshots** and per-step `ok | error | skipped`,
  stop-on-first-failure per device.
- **Idempotent:** re-planning a just-applied policy yields an empty plan; an unchanged
  `policy_hash` short-circuits. Applying across a group fans out per-device (plan 22/24 bounded
  fan-out).

## Part 5 — Drift detection + reconcile

- Periodic (scheduled job) diff of actual-vs-desired using plan 24's drift primitive → mark
  `drifted`, emit an edge-triggered alert, and offer reconcile (`apply_stored`).
- Reconcile is **pending-by-default** (operator applies) with an opt-in `autoApply: true` per policy
  for hands-off fleets — mirroring ServerKit's `autoDeploy` gate.

## Part 6 — Scaffold (reverse: YAML from live state)

- Render a `devicekit.yaml` from a live device's current apps/automations/settings so an existing
  fleet can be captured, then edited. **Secrets never inline** — emit `fromSecret: <vault-ref>`
  (plan 20) or `generate: true` → generate + store in vault + rewrite as a ref.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 | `devicekit.yaml` schema + validator + normalize | desired state is declarable + validated |
| 2 | `FleetPolicy` persistence (raw + normalized + sha256 + status) scoped to device/group | policy is durable + hashed |
| 3 | plan: desired-vs-live diff → ordered steps + hard blockers (honesty rule) | dry-run is safe + explicit |
| 4 | apply as a job (snapshots, idempotent, per-device fan-out) | policy → real device state |
| 5 | drift detection (shared with plan 24) + reconcile (pending-by-default, opt-in autoApply) | drift is visible + fixable |
| 6 | scaffold YAML from live state (secrets → `fromSecret`) | adopt an existing fleet |

Phases 1→2→3→4 sequential. Phase 5 needs 4 (+ plan 24's drift primitive). Phase 6 needs 1+2
(+ plan 20 vault).

## Decisions to make while executing (log, don't stop)

- **Policy scope granularity:** per-device vs per-group-with-per-device-overrides. Support group +
  override (matches how fleets are actually managed).
- **autoApply default:** off (recommended — MDM changes should be intentional) vs on. Off; make it
  an explicit per-policy opt-in that's audited.
- **GitOps source:** store YAML in the DB (v1) vs pull from a git repo on push-webhook (plan 22).
  Start DB-stored; a git-push reconcile trigger is a natural follow-on via the plan-22 webhook.

## Out of scope

- **OS-level configuration locking / MDM device-admin APIs.** Policy is enforced by the agent +
  drivers in userland, not by Android Device Owner provisioning (a much larger, rooted/enrolled-only
  effort).
- **Auto-authoring app adapters** from a running app (plan 18 named this out of scope too).
- **Cross-policy inheritance trees.** Group + per-device override only; no deep template
  inheritance in v1.

## ServerKit source map (for implementers)

- Spec + schema: `backend/app/services/manifest_spec_service.py`, `docs/serverkit-yaml.schema.json`,
  `docs/SERVERKIT_YAML.md`
- Persist: `backend/app/services/manifest_persistence_service.py`,
  `backend/app/models/application_manifest.py` (status `pending/applied/drifted/error`)
- Plan + apply: `backend/app/services/manifest_apply_service.py` (`_STEP_ORDER`, blockers, snapshots,
  idempotent hash short-circuit)
- Reconcile: `backend/app/services/manifest_sync_service.py` (push re-read, `autoDeploy` gate)
- Scaffold: `backend/app/services/manifest_scaffold_service.py` (`fromSecret` / `generate`)
- **Design details most worth stealing:** the plan-time **blockers ("honesty rule")**, the
  **idempotent unchanged-hash short-circuit**, and **secrets-as-refs-never-inline**.
