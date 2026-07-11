"""App-driver framework (plan 18): provisioning, version-adapter resolution, and device version
policy — the reusable ``devicekit_sdk.appdriver`` core, exercised without a phone.

A tiny fake host stands in for the Client composite: ``install_apk`` returns success/failure and
``run_adb_command`` answers ``dumpsys package`` with whatever version the test says is installed.
That is enough to prove the whole model — pin verification, per-device adapter resolution, the
three distinct unsupported outcomes, and the policy ceiling — deterministically. Live UI driving
on a real drifting app is verified separately on hardware.
"""
import time
import hashlib

import pytest

import devicekit_sdk
from devicekit_sdk import appdriver
from devicekit.db import session_scope
from devicekit.models import InstalledExtension
from devicekit.mixins.extensions import ExtensionsMixin
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin

SLUG = "test-driver"
PKG = "com.example.app"
APK = b"FAKE-APK-BYTES-v12"
APK_SHA = hashlib.sha256(APK).hexdigest()


class _Host(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    """Minimal composite: real extension/automation plumbing, faked device I/O."""

    def __init__(self):
        self.install_ok = True
        self.installed = {}         # package -> versionName the device reports after install
        self.adb_calls = []
        self.uninstalled = []
        self.taps = []              # (device_id, text) for click_by_text
        self.present = set()        # (device_id, text) that exists_by_text should find
        self.opened = []            # (device_id, package) for app_start

    def broadcast(self, *a, **k):
        pass

    def get_devices(self):
        return []

    def get_device(self, device_id):
        host = self

        class _Dev:
            def app_start(self, package):
                host.opened.append((device_id, package))
        return _Dev()

    # --- faked adb / app management --------------------------------------------------
    def install_apk(self, apk_path, device=None):
        return (True, "Success") if self.install_ok else (False, "INSTALL_FAILED [-4]")

    def run_adb_command(self, args, device=None):
        self.adb_calls.append((args, device))
        if isinstance(args, list) and "dumpsys" in args and "package" in args:
            pkg = args[-1]
            v = self.installed.get(pkg)
            return f"  Package [{pkg}]\n    versionName={v}\n" if v else ""
        if isinstance(args, list) and args and args[0] == "uninstall":
            self.uninstalled.append(args[-1])
            self.installed.pop(args[-1], None)
            return "Success"
        return ""

    # --- faked UI primitives (used by adapter step helpers) --------------------------
    def click_by_text(self, text, device_id):
        self.taps.append((device_id, text))
        return f"tapped {text}"

    def exists_by_text(self, text, device_id, timeout=5.0):
        return (device_id, text) in self.present


def _make_host():
    c = _Host()
    c.init_extensions()
    devicekit_sdk.set_host(c)
    # Register the driver extension row so the permission gate lets it touch devices.
    with session_scope() as s:
        now = time.time()
        s.add(InstalledExtension(
            slug=SLUG, version="1.0.0", display_name="Test Driver", category="integration",
            manifest={"name": SLUG, "permissions": ["adb", "device.control", "network"],
                      "device_requirements": {"package": PKG, "supported_versions": ">=12.0.0 <14.0.0"}},
            permissions=["adb", "device.control", "network"], status="active",
            installed_at=now, updated_at=now))
    return c


# ---------------------------------------------------------------------- provisioning (Part 1)
def test_provision_pins_installs_and_records(fresh_db):
    host = _make_host()
    host.installed[PKG] = "12.5.0"   # what the pinned APK reports once installed
    rec = appdriver.provision(SLUG, "dev-A", package=PKG, apk_bytes=APK,
                              expected_sha256=APK_SHA, expected_version="12.5.0", serial="R9-A")
    assert rec["status"] == "ok"
    assert rec["version_name"] == "12.5.0" and rec["sha256"] == APK_SHA and rec["serial"] == "R9-A"
    # Recorded in the extension-owned table and queryable for a fleet view.
    assert appdriver.get_provision(SLUG, "dev-A")["status"] == "ok"
    assert [p["device_id"] for p in appdriver.list_provisions(SLUG)] == ["dev-A"]


def test_provision_checksum_mismatch_refuses(fresh_db):
    host = _make_host()
    with pytest.raises(appdriver.ProvisionError) as ei:
        appdriver.provision(SLUG, "dev-A", package=PKG, apk_bytes=APK, expected_sha256="deadbeef")
    assert "checksum mismatch" in str(ei.value).lower()
    # Nothing recorded — we refused before touching the device.
    assert appdriver.get_provision(SLUG, "dev-A") is None


def test_provision_install_failure_records_and_raises(fresh_db):
    host = _make_host()
    host.install_ok = False
    with pytest.raises(appdriver.ProvisionError):
        appdriver.provision(SLUG, "dev-A", package=PKG, apk_bytes=APK, expected_sha256=APK_SHA)
    assert appdriver.get_provision(SLUG, "dev-A")["status"] == "install_failed"


def test_provision_version_mismatch_is_surfaced(fresh_db):
    host = _make_host()
    host.installed[PKG] = "11.9.0"   # device ended up on a different build than pinned
    rec = appdriver.provision(SLUG, "dev-A", package=PKG, apk_bytes=APK,
                              expected_sha256=APK_SHA, expected_version="12.5.0")
    assert rec["status"] == "version_mismatch" and rec["version_name"] == "11.9.0"


def test_installed_version_reads_dumpsys(fresh_db):
    host = _make_host()
    host.installed[PKG] = "13.1.2"
    assert appdriver.installed_version(SLUG, "dev-A", PKG) == "13.1.2"
    assert appdriver.installed_version(SLUG, "dev-A", "com.absent") is None


def test_provisioned_table_is_namespaced(fresh_db):
    _make_host()
    assert appdriver.provisioned_table(SLUG).name == "ext_test_driver_provisioned"
