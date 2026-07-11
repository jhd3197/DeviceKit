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
