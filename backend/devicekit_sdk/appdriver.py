"""App-driver framework (plan 18) — the reusable core an extension imports to *provision* a
third-party app onto devices and *drive* it through UI drift across a fleet.

Two hard truths of automating an app you don't control, made into one small library:

1. **The app must be present, at a known build.** :func:`provision` pushes a user-supplied,
   hash-pinned APK onto a device, installs it, verifies the installed ``versionName``, and
   records the result in the extension-owned ``ext_<slug>_provisioned`` table.
2. **The app's UI drifts across versions.** A :class:`VersionAdapter` binds a named flow
   (``connect``, ``disconnect``, …) to a version range and an *ordered list of steps* — and
   two adapters for the same flow may differ in selectors, step count, and order.
   :class:`AppDriver` resolves the adapter *per device per call* from the installed version and
   **fails loud** when nothing matches — never a blind tap on a drifted app.

Every device touch is permission-gated through the SDK (:func:`devicekit_sdk.device_control`),
so an app-driver extension declares ``device.control`` + ``adb`` and the gate enforces it. The
whole surface is re-exported from :mod:`devicekit_sdk` (``from devicekit_sdk import appdriver``).

This module owns no app-specific knowledge — ``devicekit-vpn`` is the worked example that
supplies the adapters and config; anyone can author another driver the same way.
"""
import os
import re
import time
import base64
import hashlib
import tempfile

from sqlalchemy import Table, Column, String, Float, select, insert, update, delete

import devicekit_sdk
from devicekit.extension_manifest import table_prefix, range_satisfies, _parse_version


# --------------------------------------------------------------------------- exceptions
class AppDriverError(RuntimeError):
    """Base class for every app-driver refusal. All of these fail loud rather than tapping a
    drifted app — the single most important rule of trustworthy UI automation (plan 18)."""


class AppNotInstalled(AppDriverError):
    """The target app is not installed on the device (nothing to drive — provision first)."""


class AppVersionUnsupported(AppDriverError):
    """The installed version is outside the extension's declared ``supported_versions`` range —
    the extension has no adapters for this build at all (app too old, or too new)."""


class NoAdapterError(AppDriverError):
    """No adapter's version range matches the installed version for the requested flow — the
    extension supports the app broadly but hasn't been taught *this* version's flow yet."""


class VersionPolicyError(AppDriverError):
    """The installed version exceeds this device's declared ``max_app_version`` ceiling — refuse
    by policy (distinct from a missing adapter) rather than drive with a newer adapter (plan 18)."""


class ProvisionError(AppDriverError):
    """Provisioning failed (checksum mismatch, install failure, or version verification failed)."""


# --------------------------------------------------------------------------- version helpers
def exceeds_ceiling(installed, ceiling):
    """True if ``installed`` is above ``ceiling`` compared *only as deep as the ceiling
    specifies*. So ``max_app_version='12'`` pins the whole 12.x line (12.9 is fine, 13.0 is not),
    ``'12.3'`` compares major.minor (12.5 exceeds), ``'12.3.4'`` compares all three. This matches
    how operators think about "stay on 12.x" — unlike a naive tuple compare where 12.5 > 12."""
    if not ceiling:
        return False
    iv = _parse_version(installed)
    cv = _parse_version(ceiling)
    n = len(cv)
    return iv[:n] > cv[:n]


def installed_version(slug, device_id, package):
    """Read the device's installed ``versionName`` for ``package`` (permission-gated
    ``device.control``). Returns ``None`` when the app isn't installed."""
    return devicekit_sdk.device_control(slug, device_id).app_version(package)


# --------------------------------------------------------------------------- provisioned table
_PROVISIONED_KEY = "provisioned"
_prov_tables = {}  # slug -> Table


def provisioned_table(slug):
    """Define (idempotently) and ensure the extension's ``ext_<slug>_provisioned`` table exists,
    returning the SQLAlchemy Core ``Table``. Namespaced under the extension so ``uninstall
    --purge`` drops it with the rest of ``ext_<slug>_*``. Safe to call from the extension's
    ``models`` register func or lazily on first provision."""
    if slug in _prov_tables:
        return _prov_tables[slug]
    md = devicekit_sdk.db.Base.metadata
    full = table_prefix(slug) + _PROVISIONED_KEY
    if full in md.tables:
        t = md.tables[full]
    else:
        t = Table(
            full, md,
            Column("device_id", String, primary_key=True),
            Column("serial", String),
            Column("package", String),
            Column("version_name", String),
            Column("sha256", String),
            Column("status", String),          # ok | version_mismatch | install_failed
            Column("provisioned_at", Float),
        )
    devicekit_sdk.db.create_all()
    _prov_tables[slug] = t
    return t


def _prov_to_dict(row):
    if not row:
        return None
    return {
        "device_id": row["device_id"], "serial": row["serial"], "package": row["package"],
        "version_name": row["version_name"], "sha256": row["sha256"],
        "status": row["status"], "provisioned_at": row["provisioned_at"],
    }


def record_provision(slug, device_id, *, serial="", package="", version_name="",
                     sha256="", status="ok"):
    """Upsert a provisioning record so the fleet view can answer "provisioned on 7/10 devices."""
    t = provisioned_table(slug)
    now = time.time()
    with devicekit_sdk.db.session() as s:
        existing = s.execute(select(t).where(t.c.device_id == device_id)).mappings().first()
        values = dict(serial=serial, package=package, version_name=version_name,
                      sha256=sha256, status=status, provisioned_at=now)
        if existing:
            s.execute(update(t).where(t.c.device_id == device_id).values(**values))
        else:
            s.execute(insert(t).values(device_id=device_id, **values))
    return get_provision(slug, device_id)


def get_provision(slug, device_id):
    t = provisioned_table(slug)
    with devicekit_sdk.db.session() as s:
        return _prov_to_dict(
            s.execute(select(t).where(t.c.device_id == device_id)).mappings().first())


def list_provisions(slug):
    t = provisioned_table(slug)
    with devicekit_sdk.db.session() as s:
        return [_prov_to_dict(r) for r in s.execute(select(t)).mappings().all()]


def clear_provision(slug, device_id):
    t = provisioned_table(slug)
    with devicekit_sdk.db.session() as s:
        s.execute(delete(t).where(t.c.device_id == device_id))


# --------------------------------------------------------------------------- provisioning
def provision(slug, device_id, *, package, apk_b64=None, apk_bytes=None,
              expected_sha256=None, expected_version=None, serial=""):
    """Provision ``package`` onto ``device_id``: verify the pinned sha256 of the user-supplied
    APK, install it (``adb install -r``), read back the installed ``versionName``, and record the
    result in ``ext_<slug>_provisioned``.

    ``apk_b64``/``apk_bytes`` carry the APK (upload-once bytes live in extension config).
    ``expected_sha256`` is the pin — a mismatch **refuses to install** (same posture as the
    extension-archive pinning). ``expected_version`` (optional) is the exact ``versionName`` the
    pinned build should report; a difference is recorded as ``version_mismatch`` (surfaced, not
    silently accepted). Returns the recorded provisioning dict. Raises :class:`ProvisionError`
    on a checksum mismatch or a failed install."""
    if apk_bytes is None:
        if not apk_b64:
            raise ProvisionError("no APK provided — supply apk_b64 (upload the APK once) or apk_bytes")
        try:
            apk_bytes = base64.b64decode(apk_b64)
        except Exception as e:
            raise ProvisionError(f"apk_b64 is not valid base64: {e}")
    if not apk_bytes:
        raise ProvisionError("APK is empty")

    digest = hashlib.sha256(apk_bytes).hexdigest()
    if expected_sha256 and digest.lower() != str(expected_sha256).lower():
        raise ProvisionError(
            f"APK checksum mismatch — refusing to install. Expected sha256 {expected_sha256}, "
            f"got {digest}.")

    control = devicekit_sdk.device_control(slug, device_id)
    fd, tmp_path = tempfile.mkstemp(suffix=".apk")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(apk_bytes)
        ok, output = control.install_apk(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not ok:
        record_provision(slug, device_id, serial=serial, package=package, version_name="",
                         sha256=digest, status="install_failed")
        raise ProvisionError(f"APK install failed on {device_id}: {output}")

    installed = installed_version(slug, device_id, package)
    status = "ok"
    if expected_version and installed and str(installed) != str(expected_version):
        status = "version_mismatch"
    return record_provision(
        slug, device_id, serial=serial, package=package, version_name=installed or "",
        sha256=digest, status=status)


def reprovision(slug, device_id, *, package, apk_b64=None, apk_bytes=None,
                expected_sha256=None, expected_version=None, serial=""):
    """Destructive remediation for a device that drifted above its ceiling: **uninstall** the app
    then re-install the pinned build (a downgrade Play won't do on its own). Gated + off by
    default at the extension layer; here it's the plain uninstall→:func:`provision` sequence."""
    devicekit_sdk.device_control(slug, device_id).uninstall_app(package)
    return provision(slug, device_id, package=package, apk_b64=apk_b64, apk_bytes=apk_bytes,
                     expected_sha256=expected_sha256, expected_version=expected_version,
                     serial=serial)


# --------------------------------------------------------------------------- version adapters (Part 2)
class VersionAdapter:
    """A named flow's implementation bound to a version range: an **ordered list of step
    callables**. Two adapters for the same flow may differ in selectors, step count, *and* order —
    because a new app version can add a whole step (a per-connect consent dialog), not just move a
    selector (plan 18). Each step is ``step(ctx) -> str`` and raises to fail loud."""

    def __init__(self, version_range, steps, name=None):
        self.version_range = version_range
        self.steps = list(steps or [])
        self.name = name

    def matches(self, version):
        return range_satisfies(version, self.version_range)

    def __repr__(self):
        return f"VersionAdapter({self.name or self.version_range!r}, {len(self.steps)} steps)"


def resolve_adapter(adapters, version):
    """Return the first adapter whose range matches ``version``; raise :class:`NoAdapterError` on no
    match. There is deliberately **no fallback** — a blind tap on a version the extension hasn't
    been taught is the exact failure this framework exists to prevent."""
    for a in adapters or []:
        if a.matches(version):
            return a
    ranges = ", ".join(a.version_range for a in (adapters or [])) or "(no adapters)"
    raise NoAdapterError(
        f"no adapter matches app version {version} (defined ranges: {ranges})")


class StepContext:
    """Handle passed to every adapter step: the resolved device, its installed version, the
    permission-gated control seam, and small UI helpers so adapters read like the plan
    (``open_app``, ``tap``, ``wait_for``). ``vars`` is a run-scoped bag one step can stash into for
    a later one."""

    def __init__(self, driver, device_id, version, variables=None):
        self.driver = driver
        self.slug = driver.slug
        self.package = driver.package
        self.device_id = device_id
        self.version = version
        self.control = devicekit_sdk.device_control(driver.slug, device_id)
        self.log = devicekit_sdk.logger(driver.slug)
        self.vars = variables if variables is not None else {}

    @property
    def _host(self):
        return devicekit_sdk.get_host()

    def open_app(self, package=None):
        return self._host.get_device(self.device_id).app_start(package or self.package)

    def tap_text(self, text):
        return self._host.click_by_text(text, self.device_id)

    def exists(self, text, timeout=5.0):
        return bool(self._host.exists_by_text(text, self.device_id, timeout=timeout))

    def shell(self, command):
        return self.control.shell(command)

    def sleep(self, seconds):
        time.sleep(seconds)


# ---- step helpers: an adapter's steps are an ordered list of these ----------------------
def open_app(package=None):
    """Launch the target app (or ``package`` if the flow drives a companion app)."""
    def step(ctx):
        ctx.open_app(package)
        return f"opened {package or ctx.package}"
    step.__name__ = "open_app"
    return step


def tap(text):
    """Tap the on-screen element whose text is ``text`` (fails if absent)."""
    def step(ctx):
        ctx.tap_text(text)
        return f"tapped '{text}'"
    step.__name__ = f"tap({text!r})"
    return step


def tap_if_present(text, timeout=2.0):
    """Tap ``text`` only if it is on screen — the "a new version added an optional consent dialog"
    primitive. A no-op (not a failure) when absent, so one adapter can tolerate a dialog that only
    some builds show."""
    def step(ctx):
        if ctx.exists(text, timeout=timeout):
            ctx.tap_text(text)
            return f"tapped optional '{text}'"
        return f"'{text}' not present — skipped"
    step.__name__ = f"tap_if_present({text!r})"
    return step


def wait_for(text, timeout=15.0):
    """Block until ``text`` appears, or fail loud after ``timeout`` — how ``wait_connected`` is
    expressed (wait for the app's connected-state label)."""
    def step(ctx):
        if not ctx.exists(text, timeout=timeout):
            raise AppDriverError(f"waited {timeout}s for '{text}' — not found")
        return f"found '{text}'"
    step.__name__ = f"wait_for({text!r})"
    return step


def assert_absent(text, timeout=3.0):
    """Fail if ``text`` is present — e.g. assert the "Connected" label is gone after disconnect."""
    def step(ctx):
        if ctx.exists(text, timeout=timeout):
            raise AppDriverError(f"'{text}' is still present")
        return f"'{text}' absent as expected"
    step.__name__ = f"assert_absent({text!r})"
    return step


def press(key):
    """Press a hardware/nav key (``back``, ``home``, …) via the gated control seam."""
    def step(ctx):
        ctx.control.press(key)
        return f"pressed {key}"
    step.__name__ = f"press({key!r})"
    return step


def sleep(seconds):
    """Fixed pause (use ``wait_for`` instead where a target is known)."""
    def step(ctx):
        ctx.sleep(seconds)
        return f"slept {seconds}s"
    step.__name__ = f"sleep({seconds})"
    return step


def shell(command):
    """Run an adb shell command on the device (gated ``adb``)."""
    def step(ctx):
        return ctx.shell(command) or f"ran: {command}"
    step.__name__ = "shell"
    return step


class AppDriver:
    """Drives a third-party app through version drift. Construct it from the flows' adapters and,
    optionally, the extension's declared ``supported_versions`` and a per-device ceiling resolver
    (plan 18 Part 3). :meth:`run` resolves the right adapter **per device per call** and fails loud
    on every unsupported outcome — it never taps a version it wasn't taught."""

    def __init__(self, slug, package, adapters, supported_versions=None, ceiling_for=None):
        self.slug = slug
        self.package = package
        self.adapters = adapters or {}          # flow name -> [VersionAdapter]
        self.supported_versions = supported_versions
        self._ceiling_for = ceiling_for         # callable(device_id) -> ceiling str | None

    def flows(self):
        return list(self.adapters.keys())

    def installed_version(self, device_id):
        return installed_version(self.slug, device_id, self.package)

    def ceiling_for(self, device_id):
        try:
            return self._ceiling_for(device_id) if self._ceiling_for else None
        except Exception:
            return None

    def resolve(self, flow, version):
        adapters = self.adapters.get(flow)
        if not adapters:
            raise NoAdapterError(f"driver has no flow '{flow}' (flows: {self.flows()})")
        return resolve_adapter(adapters, version)

    def check_version(self, device_id, *, ceiling=None):
        """Read the installed version and run the three-gate funnel, returning the version string.
        Each unsupported outcome raises its own :class:`AppDriverError` subclass so callers can
        message them distinctly — *app-not-installed*, *outside supported range*, *over policy
        ceiling* — before any adapter runs. Order is a funnel: is the app even in scope for this
        extension → is it within this device's policy → (later) does a flow adapter match."""
        version = self.installed_version(device_id)
        if version is None:
            raise AppNotInstalled(
                f"{self.package} is not installed on {device_id} — provision it first")
        if self.supported_versions and not range_satisfies(version, self.supported_versions):
            raise AppVersionUnsupported(
                f"{self.package} {version} on {device_id} is outside supported "
                f"{self.supported_versions} — this extension has no adapters for it")
        ceiling = ceiling if ceiling is not None else self.ceiling_for(device_id)
        if exceeds_ceiling(version, ceiling):
            raise VersionPolicyError(
                f"{self.package} {version} on {device_id} exceeds the device ceiling "
                f"{ceiling} — refusing by policy (reprovision to the pinned build to remediate)")
        return version

    def run(self, flow, device_id, *, ceiling=None, variables=None):
        """Resolve the adapter for this device's installed version and run its steps in order.
        Returns ``{flow, device_id, version, adapter, steps, vars}``. Raises a specific
        :class:`AppDriverError` on any unsupported outcome — the caller alerts, it never taps."""
        version = self.check_version(device_id, ceiling=ceiling)
        adapter = self.resolve(flow, version)          # raises NoAdapterError on no match
        ctx = StepContext(self, device_id, version, variables=variables)
        results = []
        for step in adapter.steps:
            results.append(step(ctx))
        return {
            "flow": flow, "device_id": device_id, "version": version,
            "adapter": adapter.name or adapter.version_range,
            "steps": results, "vars": ctx.vars,
        }
