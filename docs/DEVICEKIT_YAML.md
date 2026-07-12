# `devicekit.yaml` — Desired-State Fleet Policy

> **Live panel state is the state; the manifest is the desired state.** A `devicekit.yaml`
> declares what a device (or group) *should* look like — DeviceKit plans the diff, applies it
> as a job, and watches for drift. Plan doc: [docs/plans/23-desired-state-fleet-policy.md](plans/23-desired-state-fleet-policy.md).

## The pipeline

| Stage | What happens | Where |
|---|---|---|
| **spec** | YAML → JSON-Schema (Draft 7) validated → normalized (stable order) → sha256 hash | `backend/devicekit/policy/spec.py` |
| **persist** | One `FleetPolicy` row: raw text + normalized + hash + status `pending → applied / drifted / error` | `POST /fleet-policies` |
| **plan** | Pure desired-vs-live diff → **ordered** steps + advisory `issues` + hard **`blockers`** | `GET /fleet-policies/<id>/plan` |
| **apply** | A `policy.apply` job: global steps, then per-device fan-out (child jobs, concurrency-capped), before/after snapshots, per-step `ok/error/skipped`, stop-on-first-failure per device | `POST /fleet-policies/<id>/apply` |
| **drift** | Scheduled re-plan every 5 min (`DEVICEKIT_POLICY_DRIFT_INTERVAL`); edge-triggered `policy.drift.detected` / `.resolved` notifications | `POST /fleet-policies/<id>/check-drift` |
| **reconcile** | Pending-by-default: an operator applies the stored spec — or the policy opts into `autoApply: true` | `POST /fleet-policies/<id>/reconcile` |
| **scaffold** | The reverse: render YAML *from* a live device to adopt an existing fleet | `POST /fleet-policies/scaffold` |

**The honesty rule:** if the plan has blockers (`apk_unsupplied`, `device_offline`,
`version_unsupported`, `extension_missing`, `secret_missing`, `adb_required`, …) the apply is
**refused** (HTTP 409). There is no `--force`; DeviceKit does nothing rather than
half-configure a device. `autoApply` never fires through blockers either.

**Idempotence:** re-planning a just-applied policy yields an empty plan, and re-applying an
unchanged `policy_hash` short-circuits without enqueueing a job. Editing the YAML flips the
policy back to `pending` (the previous `applied_hash` is kept for drift comparison).

## Format

```yaml
version: 1                       # required, always 1
name: kiosk-fleet                # optional; defaults from the API call or target

target:                          # exactly ONE of:
  device: R9TT311P25N            #   a single device id / serial
  # group: <device-group-id>     #   a device group (plan 07 fleet registry)
  # fql: "android_version >= 13 AND online = true"   # an FQL selection

autoApply: false                 # opt-in self-reconcile on the drift edge (default off)

apps:                            # desired apps (plan 18 app-driver provisioning)
  - package: com.expressvpn.vpn
    version: "12.4.0"            # exact pin, or a range ("">=12.4"", "12.*")
    extension: devicekit-vpn     # the owning app-driver extension — the provision path

automations:                     # plan 22 schedules, per target device
  - automation: nightly-cleanup  # automation id or exact name
    enabled: true                # false = ensure the schedule is disabled
    schedule:
      intervalMinutes: 30

settings:                        # adb shell settings put <ns> <key> <value>
  system:
    screen_brightness: 128
  global:
    stay_on_while_plugged_in: 3
  secure: {}

extensions:                      # must be installed + active (global, not per-device)
  - devicekit-vpn

overrides:                       # per-device tweaks for group/FQL targets (merge-by-key)
  ZY22J8F4FJ:
    settings:
      system: {screen_brightness: 255}
```

Canonical keys are camelCase; snake_case aliases (`auto_apply`, `interval_minutes`,
`from_secret`) are accepted and normalized. Unknown keys are rejected.

### Secrets — never inline

A setting value may reference the plan-20 vault instead of embedding the value:

```yaml
settings:
  system:
    lock_pin:
      fromSecret: {vault: fleet-secrets, key: LOCK_PIN}   # vault by slug or id
    api_token:
      fromSecret: {vault: fleet-secrets, key: API_TOKEN}
      generate: true             # mint + store on first apply if the secret doesn't exist
```

Plan output masks secret values; apply re-resolves the ref at execution time. Scaffold
redacts sensitive-looking keys (`*pin*`, `*password*`, `*token*`, …) to bare `fromSecret`
refs — it never emits `generate: true` itself, so adopting a device can't silently rotate a
live credential.

## Step ordering

Steps execute per the `_STEP_ORDER` weight map: `attach_extension` (global, first — DeviceKit
provisioning rides the app's driver extension, a deliberate deviation from ServerKit's
order) → `provision_app` → `configure_setting` → `enable_automation`.

## v1 limits

- App and settings enforcement need the device **ADB-reachable** (agent-only transport is a
  plan-time blocker). Automations + extensions enforce without ADB.
- Group + per-device override only — no inheritance trees.
- Policies are DB-stored; a git-push reconcile trigger is a natural follow-on via the
  plan-22 webhook.
- No OS-level/MDM device-owner locking — enforcement is agent/driver userland.
