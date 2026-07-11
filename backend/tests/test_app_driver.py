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
        self.installed = {}         # package -> versionName (applies to any device unless overridden)
        self.versions = {}          # (device_id, package) -> versionName (per-device override)
        self.adb_calls = []
        self.uninstalled = []
        self.taps = []              # (device_id, text) for click_by_text
        self.present = set()        # (device_id, text) that exists_by_text should find
        self.opened = []            # (device_id, package) for app_start

    def set_installed(self, device_id, version, package=PKG):
        """Simulate a specific build on one device (mixed-version fleet tests)."""
        self.versions[(device_id, package)] = version

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
            v = self.versions.get((device, pkg), self.installed.get(pkg))
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


# --------------------------------------------------------------- version adapters (Part 2)
from devicekit_sdk.appdriver import (  # noqa: E402
    VersionAdapter, AppDriver, open_app, tap, tap_if_present, wait_for,
)


def _driver(ceiling_for=None):
    """connect flow with two adapters — 13.x adds a per-connect consent dialog (extra step)."""
    adapters = {
        "connect": [
            VersionAdapter(">=12.0.0 <13.0.0",
                           [open_app(), tap("Connect"), wait_for("Connected")], name="12.x"),
            VersionAdapter(">=13.0.0 <14.0.0",
                           [open_app(), tap("Connect"), tap_if_present("Allow"), wait_for("Connected")],
                           name="13.x"),
        ],
        "disconnect": [
            VersionAdapter(">=12.0.0 <14.0.0", [open_app(), tap("Disconnect")], name="all"),
        ],
    }
    return AppDriver(SLUG, PKG, adapters, supported_versions=">=12.0.0 <14.0.0",
                     ceiling_for=ceiling_for)


def test_adapter_resolution_by_version(fresh_db):
    _make_host()
    d = _driver()
    assert d.resolve("connect", "12.4.0").name == "12.x"
    assert d.resolve("connect", "13.2.0").name == "13.x"


def test_adapter_gap_has_no_match(fresh_db):
    _make_host()
    # Adapters for 12.0–12.5 and 13.x leave a gap at 12.7 — resolve must fail loud, not snap to a
    # neighbouring range.
    d = AppDriver(SLUG, PKG, {"connect": [
        VersionAdapter(">=12.0.0 <12.5.0", [tap("Connect")], name="early-12"),
        VersionAdapter(">=13.0.0 <14.0.0", [tap("Connect")], name="13.x"),
    ]})
    assert d.resolve("connect", "12.2.0").name == "early-12"
    with pytest.raises(appdriver.NoAdapterError):
        d.resolve("connect", "12.7.0")


def test_no_adapter_fails_loud_not_a_tap(fresh_db):
    host = _make_host()
    host.installed[PKG] = "13.5.0"
    # A driver whose connect flow only has a 12.x adapter has nothing for 13.5.
    d = AppDriver(SLUG, PKG, {"connect": [
        VersionAdapter(">=12.0.0 <13.0.0", [open_app(), tap("Connect")], name="12.x")]},
        supported_versions=">=12.0.0 <14.0.0")
    with pytest.raises(appdriver.NoAdapterError) as ei:
        d.run("connect", "dev-A")
    assert "13.5.0" in str(ei.value)
    assert host.taps == []          # never tapped a version it wasn't taught


def test_mixed_version_fleet_each_device_its_own_adapter(fresh_db):
    """The headline claim: one driver, two phones on different versions, each Just Works."""
    host = _make_host()
    host.set_installed("phone-A", "12.4.0")
    host.set_installed("phone-B", "13.2.0")
    host.present |= {("phone-A", "Connected"), ("phone-B", "Connected"), ("phone-B", "Allow")}
    d = _driver()

    ra = d.run("connect", "phone-A")
    rb = d.run("connect", "phone-B")
    assert ra["adapter"] == "12.x" and rb["adapter"] == "13.x"
    # phone-B ran the extra consent step; phone-A never saw "Allow".
    assert ("phone-B", "Allow") in host.taps
    assert ("phone-A", "Allow") not in host.taps
    assert ("phone-A", "Connect") in host.taps and ("phone-B", "Connect") in host.taps


def test_tap_if_present_skips_when_absent(fresh_db):
    host = _make_host()
    host.set_installed("phone-B", "13.2.0")
    host.present |= {("phone-B", "Connected")}          # "Allow" dialog NOT shown this time
    d = _driver()
    r = d.run("connect", "phone-B")
    assert r["adapter"] == "13.x"
    assert ("phone-B", "Allow") not in host.taps        # optional step no-oped, run still succeeded
    assert ("phone-B", "Connect") in host.taps


def test_app_not_installed_is_distinct(fresh_db):
    _make_host()                                        # no version set for the package
    d = _driver()
    with pytest.raises(appdriver.AppNotInstalled):
        d.run("connect", "dev-A")


def test_version_outside_supported_range_is_distinct(fresh_db):
    host = _make_host()
    host.installed[PKG] = "14.2.0"                      # above the extension's declared support
    d = _driver()
    with pytest.raises(appdriver.AppVersionUnsupported) as ei:
        d.run("connect", "dev-A")
    assert "14.2.0" in str(ei.value)
    assert host.taps == []


def test_wait_for_timeout_fails_loud(fresh_db):
    host = _make_host()
    host.set_installed("dev-A", "12.4.0")               # "Connected" never appears
    d = _driver()
    with pytest.raises(appdriver.AppDriverError) as ei:
        d.run("connect", "dev-A")
    assert "Connected" in str(ei.value)


# --------------------------------------------------------------- device version policy (Part 3)
def test_over_ceiling_refuses_distinct_from_no_adapter(fresh_db):
    host = _make_host()
    host.set_installed("dev-A", "13.2.0")               # a version the driver HAS an adapter for
    host.present |= {("dev-A", "Connected")}
    # Pin this device to the 12.x line; 13.2 exceeds it -> policy refusal, NOT a missing adapter.
    d = _driver(ceiling_for=lambda dev: "12")
    with pytest.raises(appdriver.VersionPolicyError) as ei:
        d.run("connect", "dev-A")
    assert "ceiling" in str(ei.value) and "13.2.0" in str(ei.value)
    assert host.taps == []                              # policy refusal never taps
    # Same device, no ceiling -> drives fine with the 13.x adapter (proves it was policy, not drift).
    assert _driver().run("connect", "dev-A")["adapter"] == "13.x"


def test_ceiling_allows_within_line(fresh_db):
    host = _make_host()
    host.set_installed("dev-A", "12.9.0")               # still on the 12.x line
    host.present |= {("dev-A", "Connected")}
    d = _driver(ceiling_for=lambda dev: "12")           # ceiling '12' pins the whole 12.x line
    assert d.run("connect", "dev-A")["adapter"] == "12.x"


def test_config_ceiling_resolver_per_device_beats_global(fresh_db):
    cfg = {"max_app_version": "13", "device_max_versions": {"pinned-dev": "12"}}
    resolver = appdriver.make_ceiling_resolver(lambda: cfg)
    assert resolver("pinned-dev") == "12"               # per-device override wins
    assert resolver("other-dev") == "13"                # falls back to the global ceiling
    cfg2 = appdriver.make_ceiling_resolver(lambda: {})
    assert cfg2("any") is None                          # no ceiling configured


def test_over_ceiling_helper(fresh_db):
    host = _make_host()
    host.set_installed("dev-A", "13.4.0")
    assert appdriver.over_ceiling(SLUG, "dev-A", PKG, "12") is True
    assert appdriver.over_ceiling(SLUG, "dev-A", PKG, "13") is False
    assert appdriver.over_ceiling(SLUG, "dev-A", PKG, None) is False


def test_reprovision_uninstalls_then_installs_pinned(fresh_db):
    host = _make_host()
    host.set_installed("dev-A", "13.9.0")               # drifted above the pinned build
    # Reprovision downgrades: uninstall removes the drifted version, install lands the pin (12.5).
    host.versions[("dev-A", PKG)] = "13.9.0"

    def _install(apk_path, device=None):
        host.versions[(device, PKG)] = "12.5.0"         # the pinned build lands after install
        return (True, "Success")
    host.install_apk = _install

    rec = appdriver.reprovision(SLUG, "dev-A", package=PKG, apk_bytes=APK,
                                expected_sha256=APK_SHA, expected_version="12.5.0")
    assert PKG in host.uninstalled                       # old build removed first
    assert rec["status"] == "ok" and rec["version_name"] == "12.5.0"
