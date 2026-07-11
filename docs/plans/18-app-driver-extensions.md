# Plan 18 — App-Driver Extensions (provisioning + version drift)

**Status:** ✅ shipped (2026-07-11) — all 5 phases. Framework lives in
`backend/devicekit_sdk/appdriver.py` (provision + version adapters + policy); the worked example is
the bundled `devicekit-vpn` extension. 33 tests (`test_app_driver.py` + `test_vpn_extension.py`).
**Inspired by:** the original ExpressVPN-style vision that opened the extension design
conversation — install an extension, have it put an app on the device, then drive that
app through automations. Plan 15 deferred it with two named prerequisites:
`device_requirements` (declare + pin a third-party APK) and version-keyed behavior
(the app's UI drifts across releases). This plan builds both, using VPN control as the
worked example but staying app-agnostic.
**Depends on:** 15 (device primitives, `automation_templates`), 13 (write tools gated —
a driver's actions change device state). Soft: 16 (documents the model), 17 (unrelated
dependency axis, but its manifest-key pattern is the template).

## The core problem this plan solves

An app-driver extension automates a *third-party app it doesn't control*. Two hard
truths follow, and both are the user's actual questions:

1. **The app must be present, at a known build.** The extension can't ship the APK
   (licensing, staleness), so it declares a requirement and provisions a user-supplied,
   hash-pinned APK onto each device.
2. **The app's UI drifts across versions.** A "Connect" button moves, a flow gains an
   extra consent screen, a selector changes. **Across a fleet, different devices may run
   different versions at the same time.** So the driver can't have one hard-coded flow —
   it needs *per-version behavior*, chosen per device at runtime.

Everything below is those two truths made concrete.

## Part 1 — `device_requirements` (declare + provision the app)

**Manifest key** — the extension declares what app it drives and which builds it
supports:

```json
"device_requirements": {
  "package": "com.expressvpn.vpn",
  "supported_versions": ">=12.0.0 <14.0.0",
  "provision": "user_supplied_apk"
}
```

- `package` — the app the driver targets. Checkable per device via the existing
  `list_installed_apps`.
- `supported_versions` — the range the extension has adapters for (see Part 2). A device
  running outside this range is *known-unsupported*, surfaced instead of silently
  attempted.
- `provision` — `user_supplied_apk` (the honest default: user uploads the APK once,
  extension pins its sha256) or `play_store` (fire a `market://` intent and let the user
  finish — no pinning, weaker guarantees).

**Consent-card surfacing** — the install/preview flow (`routes/extensions.py` preview +
the frontend consent card from plan 04) shows the device requirement up front: "this
extension drives com.expressvpn.vpn; you must supply an APK." No surprise device changes.

**Provisioning, per device** — a `provision(device_id)` tool/step: push the pinned APK
(existing file-push primitive) → install → verify installed `versionName` matches the
pin → record in an extension-owned table `ext_<slug>_provisioned` (serial, versionName,
sha256, provisioned_at, status). Fleet view can then answer "provisioned on 7/10
devices." The APK bytes live in extension config (upload once), hash-pinned exactly like
the extension-archive sha256 pinning that already exists.

## Part 2 — Version-keyed behavior (the drift answer)

This is the heart of your question — *yes, "in this version do X, in that version do Y,
or this extra step" is exactly the model*, and it has to work when different devices in
one fleet run different versions.

**Adapters, not just selectors.** A naive design keys only *selectors* by version
(`connect_button` = this-or-that resource id). That's not enough — sometimes a new
version adds a whole **step** (a consent dialog, a login wall). So the unit is an
**adapter**: a named flow (`connect`, `disconnect`, `status`) bound to a **version
range**, defining an *ordered list of steps*. Two adapters for the same flow can differ
in selectors, in step count, and in order.

```python
# extension defines, per flow, a list of version-ranged adapters
ADAPTERS = {
  "connect": [
    VersionAdapter(">=12.0.0 <13.0.0", steps=[
      open_app, tap("Connect"), wait_connected,
    ]),
    VersionAdapter(">=13.0.0 <14.0.0", steps=[
      open_app, tap("Connect"),
      tap_if_present("Allow"),        # 13.x added a per-connect consent dialog
      wait_connected,
    ]),
  ],
  ...
}
```

**Runtime resolution, per device.** Every driver call:

1. read the device's installed `versionName` (`list_installed_apps` — cheap, already
   exists);
2. pick the adapter whose range matches;
3. **no match → fail loudly** ("app version 14.2 has no adapter for `connect`"), never
   blind-tap. This is the single most important rule — a silent no-op on a drifted app
   is the failure mode that makes UI automation untrustworthy;
4. run the adapter's steps.

Because resolution is per device per call, a fleet where phone A runs 12.x and phone B
runs 13.x Just Works — each gets its own adapter. That directly answers "maybe one user
has the app in one version vs another."

**Shipping new-version support = adding an adapter + bumping `supported_versions`**, which
rides the normal extension-update flow (plan 17's registry, plan 15's self-heal). No host
changes when an app updates — the extension absorbs the drift.

## Part 3 — Device version policy ("this device can't go above X")

Your other case: pinning a device to a ceiling. Two layers, because "can't upgrade" is
partly enforceable and partly declared:

- **Pinned provisioning** — provisioning installs an exact hash-pinned build, and Play
  generally won't auto-update an app it didn't install (installer = shell, common on
  fleet devices without Play accounts). So the pinned version *tends to stick* on its
  own.
- **Declared ceiling** — config `max_app_version` per device (or per device group via
  FQL): the extension records the ceiling and, on each run, if the device's installed
  version exceeds it, **refuses to drive and alerts** rather than using a newer adapter.
  That covers "this device must stay on 12.x" even if something upgraded it — the driver
  treats over-ceiling as unsupported-by-policy, distinct from unsupported-by-missing-adapter.
- **Re-pin on drift (optional remediation)** — if a device drifted above its ceiling, a
  `reprovision` step can downgrade-reinstall the pinned APK (uninstall + install the
  pinned build). Gated (it's destructive), off by default.

So the version story has three distinct "unsupported" outcomes, each with a clear
message: *no adapter* (extension hasn't been taught this version), *over policy ceiling*
(device pinned below installed version), and *below `device_requirements` range* (app too
old). None of them silently taps.

## Worked example — `devicekit-vpn`

**Category:** `integration` · **Permissions:** `device.control`, `network` ·
**Requires:** `com.expressvpn.vpn` (or a configurable package)

- **Provision:** user uploads the ExpressVPN APK; `vpn__provision(device)` pins + installs.
- **Adapters:** `connect` / `disconnect` / `status` flows, version-ranged as above.
- **Config:** `allowed_countries`, `preferred_location`, `apk_sha256`, per-device
  `max_app_version`, `check_interval`.
- **AI tools / step types:** `vpn_connect(location)` (gated — changes network path),
  `vpn_disconnect`, `vpn_status`. `connect` validates the requested country against
  `allowed_countries` so even the AI can't route to a non-approved exit.
- **The steady-state automation** (shipped as an `automation_template`, plan 15):
  status-check → **verify egress** (device `curl`s its public IP, geo-check — the app UI
  alone can't reveal wrong-country-connected) → remediate (`vpn_connect(preferred)`) →
  re-verify → `screenshot_assert` as evidence. Wrong adapter/version → alert via
  `devicekit-webhook-notify`, don't tap.

Intent-API alternative noted for completeness: apps with real automation intents
(WireGuard `SET_TUNNEL_UP/DOWN`, OpenVPN-for-Android `de.blinkt.openvpn.api`) don't need
adapters at all — the driver can offer an *intent backend* (stable) and a
*UI-automation backend* (adapters) and pick per app. ExpressVPN has no public intent API,
so it's the UI-automation case; that's what makes it the honest stress test.

## Phases

| Phase | Delivers | Proves | Status |
|---|---|---|---|
| 1 | `device_requirements` manifest key + consent-card surfacing + `provision()` (pinned APK push/install/verify + `ext_*_provisioned` table) | declare + install a 3rd-party app safely | ✅ |
| 2 | Version-adapter framework: `VersionAdapter`, per-device resolution, three distinct unsupported outcomes | drift handled per device, fails loud | ✅ |
| 3 | Device version policy: `max_app_version`, over-ceiling refusal, optional gated `reprovision` | "this device can't go above X" | ✅ |
| 4 | `devicekit-vpn`: adapters + config + gated tools + verify-egress automation template | the whole model on a real drifting app | ✅ |
| 5 | registry entry + EXTENSIONS.md "app-driver extensions" section (provisioning, adapters, policy) | others can author drivers | ✅ |

Phases 1→2→3 are sequential (each builds the prior's concept); phase 4 needs all three;
phase 5 last.

**Deviations (as shipped):** the framework is a reusable SDK module (`devicekit_sdk.appdriver`,
re-exported), not vpn-only, so any extension can author a driver — that's what makes phase 5's
"others can author drivers" real. `provision` uses the atomic `adb install -r` (push+install in one)
rather than a separate file-push then install. The verify-egress template uses a `screenshot`
evidence step (not `screenshot_assert`, which needs a per-device baseline the user captures first),
and folds status-check → verify → remediate → re-verify into a `vpn_ensure_egress` step so the
linear automation engine can express the "only reconnect if wrong" loop. "Wrong adapter/version →
alert, don't tap" is realized by the driver raising a distinct `AppDriverError`, which fails the run
loud → `automation.run.failed` on the plan-06 notification bus (no hard dependency on
`devicekit-webhook-notify`).

## Out of scope

- **Bundling any third-party APK in the extension archive.** Always user-supplied +
  hash-pinned. Licensing and staleness make bundling a non-starter.
- **Auto-authoring adapters from a running app** (record-and-replay UI capture). Nice
  future tooling, but adapters are hand-written here.
- **Rooted/system-level version *locking*** (blocking OS-level updates). Out of reach for
  a userland agent; the ceiling is policy-enforced by the driver, not by the OS.
