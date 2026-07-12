# Plan 25 — Agent Lifecycle, OTA & Backup/DR

**Status:** 🚧 in progress — phases 1–2 shipped (backend + frontend + Kotlin source; APK rebuild pending)
**Inspired by:** three ServerKit lessons — two for the agent, one for the platform's own
durability.
1. **The agent trust boundary** (`docs/AGENT_SURVEY_SPEC.md`): the agent enforces a **fixed
   allowlist of read-only primitives**; the panel is treated as **untrusted** and may only
   *combine* primitives — never name a shell command or exfiltrate a whole file. Pair with
   `agent_registry.send_command`'s capability negotiation: compose health/actions from commands
   every deployed agent already speaks, and add batched probes only as a **capability-gated
   optimization** with the composed path as a permanent fallback.
2. **The agent-plugin *schema*** (`models/agent_plugin.py`): capabilities + typed permissions +
   resource limits + a dependency graph — a well-designed contract. But ServerKit's on-device
   runtime is explicitly *"not implemented yet"* (`agent_plugin_service.install_plugin` returns an
   error). So copy the **contract**, not the stalled runtime; real sandboxed on-device code is
   greenfield in both projects.
3. **Backup with restore drills** (`docs/BACKUP_PROTECTION.md`): *"a backup you've never restored is
   an assumption, not a safety net."* A verify ladder (`none → listed → hashed → drilled`, the hash
   compared against a **stored** manifest, never recomputed from the same possibly-corrupt file) and
   — the standout — `backup_drill_service.py`: restore the latest backup into a **throwaway scratch
   DB**, verify it, tear it down, **never touching live**.
**Depends on:** 07/29 (HMAC + signing — OTA needs signed APKs; the capability map), 05/25 (rollout +
drills as scheduled jobs), 08 (agent health metrics). DeviceKit-specific: the APK is **built and
flashed by hand today** (`build-agent-apk` skill) — untenable past a handful of devices.

## The questions this plan answers

- **"How do I roll a new agent to 200 phones without touching them?"** OTA: the backend hosts
  signed APK versions; agents self-update on a rollout policy (canary → staged → full + rollback),
  delivered as scheduled jobs. Greenfield — neither project has it, so it's a differentiator.
- **"Can the server push arbitrary commands to a device?"** No — the agent enforces a fixed
  read-only primitive allowlist and the server may only compose them. This formalizes the
  FLEET_CONTRACT trust boundary for Android.
- **"What happens if my DeviceKit DB is corrupted or the box dies?"** Backup + restore of
  DeviceKit's *own* state, with a scheduled **restore drill** that proves the backup actually
  restores — surfaced as a health check (plan 24).

## Part 1 — Agent-enforced primitive allowlist

- Ship read-only survey/health primitives the **device** enforces (file-exists, glob, unit/app
  status, process list, metrics, package/version list). The server composes them; it can never name
  a raw shell command or pull a whole file. Env/secret files are listed **by path only, never
  read**. This is the trust boundary the plan-24 doctor probes already assume.

## Part 2 — Capability & version negotiation

- Agents advertise version + capabilities (Android API level, root, installed frameworks — the
  FLEET_CONTRACT already carries a capability map). Richer batched probes are negotiated by
  capability with the composed path as a permanent fallback, so an old agent keeps working forever.
- A fleet view of **which agent version is on which device**, roll-forward/back.

## Part 3 — OTA agent updates (greenfield)

- Backend hosts **signed** APK versions (HMAC/signing from plan 07/29). Agents self-update on a
  **rollout policy**: canary → staged → full, with rollback, delivered as scheduled jobs (plan 05)
  so it's restart-safe + observable. Crash-loop backoff on a bad update.

## Part 4 — Onboarding state machine

- Formalize enrollment: `pending → validating → provisioning → ready | failed`, advanced on the job
  bus with an ordered progress log (replaces today's ad-hoc pairing). Ties into plan 18 provisioning
  and plan 23 desired-state (a newly-ready device gets its group policy applied).

## Part 5 — Agent-plugin contract (schema now, runtime later)

- Adopt ServerKit's manifest schema as the **declaration**: `capabilities` (metrics / health_checks
  / commands / scheduled_tasks / event_hooks), typed `permissions` (filesystem / network / process /
  system), resource limits (`max_memory_mb` / `max_cpu_percent`), and a dependency graph.
- **Real on-device execution stays a stretch** — deliver the contract + the `send_command`
  capability-negotiation delivery boundary; sandboxed code-on-agent is a genuine L and greenfield in
  both projects.

## Part 6 — Backup / DR of DeviceKit's own state

- Back up DB + config → tarball + `manifest.json` (per-artifact **sha256**, tool versions, chain
  refs). **Verify ladder:** `listed` (`tar -t` readable) + `hashed` (matches the **stored** hash,
  not one recomputed from the same file) run automatically after every backup.
- **Restore drill** (`backup_drill_service.py`) — the standout: on a cadence, restore the latest
  backup into a **throwaway scratch SQLite DB / temp dir**, probe-verify (file count + bytes + table
  count), tear down — never touching the live DB. Hard guards to copy: **free-space precheck** →
  loud `skipped_no_space` (never a silent pass); **vacuous-drill guard** (a 0-file restore fails
  loud instead of earning `drilled`); scratch DB always dropped in a `finally`.
- Surface `restore_confidence` as a plan-24 doctor check with **edge-triggered** alerts (fires once
  on drill-failed, once on recovery).
- **Related cleanup:** apply scrub-first discipline to the existing debug bundles — settings as
  **keys + types only, never values**; `_scrub()` over free text (JWTs, bearer/basic headers,
  `key=secret`); each collector isolated so one broken collector can't sink the bundle.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 ✅ | agent-enforced read-only primitive allowlist (server composes, never pushes shell) | device trust boundary |
| 2 ✅ | capability/version negotiation + fleet "agent version where" view | old agents work forever; batched probes opt-in |
| 3 | OTA agent updates: signed APK versions + rollout policy (canary→staged→full+rollback) as jobs | reflash the fleet without touching it |
| 4 | onboarding state machine (`pending→…→ready`) on the job bus | formal enrollment, policy-on-ready |
| 5 | agent-plugin manifest contract (capabilities + typed perms + limits + deps); runtime deferred | a declarable on-device plugin surface |
| 6 | backup/DR of own state: tarball + manifest + verify ladder + **restore drill** + scrub-first bundles | the platform can survive its own box dying |

Phases 1→2 sequential (2 builds on the primitive set). Phase 3 needs 2 (version negotiation) + plan
07/29 signing. Phase 4 needs plan 05. Phase 5 is independent (schema only). Phase 6 is independent
of the agent work — can land any time.

## Decisions to make while executing (log, don't stop)

- **OTA delivery:** agent-pull from a signed backend endpoint (recommended) vs push. Pull + rollout
  policy — pull survives NAT and flaky links.
- **Agent-plugin runtime:** ship schema-only now (recommended) vs attempt on-device execution.
  Schema-only; real sandboxed execution is a separate greenfield plan.
- **Backup target:** local + optional offsite (S3-compatible, ServerKit's `backup_offsite_service`)
  vs local only. Local first; offsite as opt-in.

## Out of scope

- **Rooted/system-level OS update control.** OTA updates the *agent*, not Android; blocking OS
  updates is out of reach for a userland agent (same boundary plan 18 drew).
- **Real sandboxed on-device plugin execution.** Contract only here; the runtime is greenfield.
- **Multi-region DR / hot standby.** Backup + restore-drill of a single instance; HA is not this
  plan.

## ServerKit source map (for implementers)

- Agent trust boundary: `docs/AGENT_SURVEY_SPEC.md`, `docs/AGENT_DOCTOR_PROBE_SPEC.md`,
  `agent_registry.send_command` (capability negotiation)
- Agent-plugin contract: `backend/app/models/agent_plugin.py`,
  `backend/app/services/agent_plugin_service.py` (**runtime is a stub — copy the schema only**)
- Onboarding: `backend/app/services/server_onboarding_service.py` (state machine on the job bus)
- Backup suite: `backup_service.py`, `backup_verify_service.py` (verify ladder),
  `backup_drill_service.py` (scratch restore, free-space precheck, vacuous-drill guard),
  `backup_offsite_service.py`, `backup_alert_service.py` (edge-trigger), `docs/BACKUP_PROTECTION.md`
- Scrub-first bundles: `backend/app/services/support_bundle_service.py` (`_scrub`, `_safe`,
  types-not-values)
- **Non-obvious correctness lessons:** compare against a *stored* hash (not one recomputed from the
  possibly-corrupt file); guard the **vacuous drill** (0 files must fail, not pass); free-space
  precheck must be a **loud skip**, never a silent pass.
