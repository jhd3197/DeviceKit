"""Pure desired-vs-live diff → ordered steps + issues + hard blockers (plan 23 part 3).

``plan_policy`` never touches a device, the DB, or the network — the mixin collects a live
snapshot first and hands it in, so the diff is deterministic and unit-testable. Output is a
dry-run plan: **ordered** action steps (``_STEP_ORDER`` weight map), advisory ``issues``, and
hard ``blockers``. Blockers refuse the apply outright — the honesty rule: DeviceKit would
rather do nothing than half-configure a device.

Step ordering deviation from the ServerKit map: ``attach_extension`` runs FIRST (weight 10),
not last — DeviceKit app provisioning is performed *by* the app's driver extension, so the
extension must be active before ``provision_app`` can succeed.
"""
from devicekit.extension_manifest import range_satisfies
from devicekit.policy.spec import effective_spec_for_device

_STEP_ORDER = {
    "attach_extension": 10,   # global: install/enable a declared extension
    "provision_app": 20,      # plan-18 driver provisioning (hash-pinned APK)
    "install_app": 30,        # reserved for non-driver installs (not emitted in v1)
    "configure_setting": 40,  # adb shell settings put <ns> <key> <value>
    "enable_automation": 50,  # plan-22 interval schedule create/update/disable
}

_RANGE_CHARS = set("<>=*, ")


def _is_exact_pin(pin):
    return not any(c in _RANGE_CHARS for c in pin)


def _pin_satisfied(installed, pin):
    """Exact pins compare literally; anything with range syntax (``>=12``, ``12.*``…) goes
    through plan 18's ``range_satisfies``."""
    if _is_exact_pin(pin):
        return installed == pin
    return range_satisfies(installed, pin)


def setting_str(value):
    """Android ``settings put`` stores strings; booleans follow the 1/0 convention."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def secret_ref_key(ref):
    return f"{ref['vault']}/{ref['key']}"


class _Plan:
    def __init__(self):
        self.steps = []
        self.issues = []
        self.blockers = []

    def step(self, kind, device_id=None, **detail):
        self.steps.append({"kind": kind, "device_id": device_id,
                           "order": _STEP_ORDER[kind], **detail})

    def issue(self, code, message, device_id=None):
        self.issues.append({"code": code, "message": message, "device_id": device_id})

    def block(self, code, message, device_id=None):
        self.blockers.append({"code": code, "message": message, "device_id": device_id})


def _plan_apps(plan, did, eff, dl, live, declared_extensions):
    for app in eff["apps"]:
        pkg, pin, slug = app["package"], app.get("version"), app.get("extension")
        installed = dl.get("apps", {}).get(pkg)
        if installed is not None and (not pin or _pin_satisfied(installed, pin)):
            continue
        if not slug:
            plan.block("no_provision_path",
                       f"{pkg} is {'missing' if installed is None else f'at {installed}'} "
                       f"but the entry names no app-driver extension to provision it", did)
            continue
        meta = live.get("app_meta", {}).get(slug) or {}
        if not meta.get("active"):
            if slug in declared_extensions:
                # The same policy attaches the extension (extensions run first), but its APK
                # config/version range are unknowable until it installs — surfaced as an
                # issue; a real problem fails the step loudly at apply.
                plan.issue("extension_pending",
                           f"{slug} attaches during this apply; APK config for {pkg} "
                           f"can't be verified until then", did)
                plan.step("provision_app", did, package=pkg, extension=slug,
                          desired_version=pin, current_version=installed)
            else:
                plan.block("extension_missing",
                           f"{pkg} needs extension {slug}, which is not installed and not "
                           f"declared in this policy's extensions", did)
            continue
        supported = meta.get("supported_versions")
        if pin and supported and _is_exact_pin(pin) and not range_satisfies(pin, supported):
            plan.block("version_unsupported",
                       f"{pkg} {pin} is outside {slug}'s adapter range ({supported})", did)
            continue
        provision = meta.get("provision") or "user_supplied_apk"
        if provision == "play_store":
            plan.block("manual_install_required",
                       f"{pkg} provisions via the Play Store; DeviceKit cannot install it "
                       f"unattended", did)
            continue
        if not meta.get("apk_supplied"):
            plan.block("apk_unsupplied",
                       f"no APK configured on {slug} to provision {pkg}", did)
            continue
        apk_version = meta.get("apk_version")
        if pin and apk_version and _is_exact_pin(pin) and apk_version != pin:
            plan.block("apk_version_mismatch",
                       f"{slug}'s configured APK is {apk_version} but the policy pins "
                       f"{pkg} at {pin}", did)
            continue
        plan.step("provision_app", did, package=pkg, extension=slug,
                  desired_version=pin, current_version=installed)


def _plan_settings(plan, did, eff, dl, live):
    for ns, kv in eff["settings"].items():
        for key, desired in kv.items():
            actual = dl.get("settings", {}).get(ns, {}).get(key)
            if isinstance(desired, dict):  # {fromSecret: {...}, generate?}
                ref = desired["fromSecret"]
                sec = live.get("secrets", {}).get(secret_ref_key(ref)) or {}
                if not sec.get("found"):
                    if desired.get("generate"):
                        plan.step("configure_setting", did, namespace=ns, key=key,
                                  value="••••••", secret=True, generate=True,
                                  from_secret=ref, current=actual)
                    else:
                        plan.block("secret_missing",
                                   f"settings.{ns}.{key} references missing secret "
                                   f"{secret_ref_key(ref)}", did)
                    continue
                want = str(sec["value"])
                if actual == want:
                    continue
                plan.step("configure_setting", did, namespace=ns, key=key,
                          value="••••••", secret=True, from_secret=ref, current=actual)
            else:
                want = setting_str(desired)
                if actual == want:
                    continue
                plan.step("configure_setting", did, namespace=ns, key=key,
                          value=want, current=actual)


def _plan_automations(plan, did, eff, dl):
    for auto in eff["automations"]:
        ref = auto["automation"]
        meta = dl.get("automations", {}).get(ref) or {}
        automation_id = meta.get("automation_id")
        if not automation_id:
            plan.block("automation_missing", f"automation '{ref}' does not exist", did)
            continue
        sched = meta.get("schedule")
        want_interval = auto["schedule"]["intervalMinutes"]
        if auto.get("enabled", True):
            if not sched:
                plan.step("enable_automation", did, action="create",
                          automation=ref, automation_id=automation_id,
                          interval_minutes=want_interval)
            elif sched.get("interval_minutes") != want_interval or not sched.get("enabled"):
                plan.step("enable_automation", did, action="update",
                          automation=ref, automation_id=automation_id,
                          schedule_id=sched["id"], interval_minutes=want_interval,
                          current_interval=sched.get("interval_minutes"),
                          currently_enabled=bool(sched.get("enabled")))
        elif sched and sched.get("enabled"):
            plan.step("enable_automation", did, action="disable",
                      automation=ref, automation_id=automation_id,
                      schedule_id=sched["id"])


def _plan_extensions(plan, spec, device_ids, live):
    """Extensions are per-install (global), not per-device — planned once. The union covers
    override-added slugs for targeted devices."""
    declared = set(spec.get("extensions") or [])
    for did in device_ids:
        declared |= set(effective_spec_for_device(spec, did)["extensions"])
    for slug in sorted(declared):
        st = live.get("extensions", {}).get(slug) or {}
        if st.get("active"):
            continue
        if st.get("installed"):
            plan.step("attach_extension", None, action="enable", extension=slug)
        elif st.get("available") is False:
            plan.block("extension_unavailable",
                       f"extension {slug} is not installed and not in the registry")
        else:
            if st.get("available") is None:
                plan.issue("registry_unknown",
                           f"registry unreachable — {slug} will attempt install at apply")
            plan.step("attach_extension", None, action="install", extension=slug)
    return declared


def plan_policy(spec, device_ids, live):
    """Diff desired (normalized spec) against a live snapshot for the resolved devices.

    Returns ``{steps, issues, blockers, devices, empty}`` with steps sorted by the
    ``_STEP_ORDER`` weight map (global extension steps first), then device, then subject."""
    plan = _Plan()
    if not device_ids:
        plan.issue("no_devices", "policy target matched no devices")
    declared_extensions = _plan_extensions(plan, spec, device_ids, live)
    for did in device_ids:
        eff = effective_spec_for_device(spec, did)
        dl = live.get("devices", {}).get(did)
        if not dl or not dl.get("present"):
            plan.block("device_missing", f"device {did} is not registered/connected", did)
            continue
        if not dl.get("online"):
            plan.block("device_offline", f"device {did} is offline", did)
            continue
        if (eff["apps"] or eff["settings"]) and not dl.get("adb"):
            plan.block("adb_required",
                       f"device {did} is agent-only; app/settings enforcement needs ADB "
                       f"transport in v1", did)
            continue
        _plan_apps(plan, did, eff, dl, live, declared_extensions)
        _plan_settings(plan, did, eff, dl, live)
        _plan_automations(plan, did, eff, dl)
    plan.steps.sort(key=lambda s: (s["order"], s["device_id"] or "",
                                   s.get("package") or s.get("key") or
                                   s.get("automation") or s.get("extension") or ""))
    for i, step in enumerate(plan.steps, 1):
        step["id"] = f"step-{i}"
    return {
        "steps": plan.steps,
        "issues": plan.issues,
        "blockers": plan.blockers,
        "devices": list(device_ids),
        "empty": not plan.steps and not plan.blockers,
    }
