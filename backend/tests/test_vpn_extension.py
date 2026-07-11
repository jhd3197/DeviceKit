"""devicekit-vpn (plan 18 phase 4): the whole app-driver model on the worked example. The APK
install, UI taps, and geo-IP curl are faked on the host, so provisioning, per-device adapter
resolution, the allowed-countries gate, version policy, and egress verification all run without a
phone. Live driving of the real ExpressVPN app is verified separately on hardware.
"""
import os
import time
import shutil
import hashlib

import pytest
from flask import Flask

import devicekit_sdk
from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools

SLUG = "devicekit-vpn"
PKG = "com.expressvpn.vpn"
APK = b"FAKE-EXPRESSVPN-APK"
APK_SHA = hashlib.sha256(APK).hexdigest()
APK_B64 = __import__("base64").b64encode(APK).decode()


class _Host(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    def __init__(self):
        self.versions = {}          # (device_id, package) -> versionName
        self.present = set()        # (device_id, text) exists_by_text finds
        self.taps = []              # (device_id, text)
        self.opened = []            # (device_id, package)
        self.egress_json = '{"status":"success","country":"United States","countryCode":"US","query":"1.2.3.4"}'
        self.install_ok = True

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

    def install_apk(self, apk_path, device=None):
        return (True, "Success") if self.install_ok else (False, "FAILED")

    def run_adb_command(self, args, device=None):
        if isinstance(args, list) and "dumpsys" in args and "package" in args:
            v = self.versions.get((device, args[-1]))
            return f"versionName={v}\n" if v else ""
        if isinstance(args, list) and args and args[0] == "shell" and "curl" in " ".join(args):
            return self.egress_json
        if isinstance(args, str) and args.startswith("shell") and "curl" in args:
            return self.egress_json
        return ""

    def click_by_text(self, text, device_id):
        self.taps.append((device_id, text))

    def exists_by_text(self, text, device_id, timeout=5.0):
        return (device_id, text) in self.present

    def set_version(self, device_id, version):
        self.versions[(device_id, PKG)] = version


@pytest.fixture(autouse=True)
def _clean():
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()


def _client(**config):
    c = _Host()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    devicekit_sdk.set_host(c)
    c.install_builtin_extension(SLUG)
    cfg = {"apk_b64": APK_B64, "apk_sha256": APK_SHA, "apk_version": "12.5.0",
           "allowed_countries": "US, CA", "preferred_location": "United States - New York"}
    cfg.update(config)
    c.update_extension_config(SLUG, cfg)
    return c


# --------------------------------------------------------------------------- install / contributions
def test_vpn_installs_and_contributes(fresh_db):
    c = _client()
    assert c.get_extension(SLUG)["status"] == "active"

    st = c.get_step_types()
    for t in ("vpn_connect", "vpn_disconnect", "vpn_status", "vpn_provision",
              "vpn_verify_egress", "vpn_ensure_egress", "vpn_reprovision"):
        assert t in st and "execute" not in st[t]

    # AI tools bound + namespaced; status is read, connect is a gated write.
    tools = build_device_tools(c, "dev-1")._tools
    assert "devicekit_vpn__connect" in tools and "devicekit_vpn__status" in tools
    assert tools["devicekit_vpn__status"].metadata["is_write"] is False
    assert tools["devicekit_vpn__connect"].metadata["is_write"] is True

    # Provisioning table exists and the egress-check template is seeded.
    assert "ext_devicekit_vpn_provisioned" in devicekit_sdk.db.Base.metadata.tables
    seeded = [a for a in c.list_automations() if f"ext:{SLUG}" in (a.get("tags") or [])]
    assert len(seeded) == 1 and seeded[0]["name"] == "VPN Egress Check"
    assert [s["type"] for s in seeded[0]["steps"]] == ["vpn_status", "vpn_ensure_egress", "screenshot"]


def test_manifest_declares_device_requirements(fresh_db):
    c = _client()
    reqs = c.get_extension(SLUG)["manifest"]["device_requirements"]
    assert reqs["package"] == PKG and reqs["provision"] == "user_supplied_apk"


def test_preview_surfaces_device_requirement_on_consent(fresh_db):
    """The consent flow (plan 18 ph1) shows the device requirement up front — no surprise install."""
    from devicekit.mixins.extensions import BUILTIN_EXTENSIONS_DIR
    c = _Host()
    c.init_extensions()
    devicekit_sdk.set_host(c)
    preview = c.preview_extension(path=os.path.join(BUILTIN_EXTENSIONS_DIR, SLUG))
    assert preview["device_requirements"]["package"] == PKG
    assert any("drives com.expressvpn.vpn" in w.lower() or "com.expressvpn.vpn" in w
               for w in preview["warnings"])


# --------------------------------------------------------------------------- provisioning
def test_provision_pins_and_records(fresh_db):
    c = _client()
    c.set_version("dev-A", "12.5.0")                 # what the pinned APK reports post-install
    from devicekit.extensions.devicekit_vpn import driver
    rec = driver.provision("dev-A", serial="R9-A")
    assert rec["status"] == "ok" and rec["version_name"] == "12.5.0"
    assert [p["device_id"] for p in driver.provisioned()] == ["dev-A"]


def test_provision_without_apk_config_refuses(fresh_db):
    c = _client(apk_b64="")                          # no APK uploaded
    from devicekit.extensions.devicekit_vpn import driver
    with pytest.raises(devicekit_sdk.appdriver.ProvisionError):
        driver.provision("dev-A")


# --------------------------------------------------------------------------- adapters (drift)
def test_connect_resolves_adapter_per_version(fresh_db):
    c = _client()
    c.set_version("phone-A", "12.4.0")
    c.set_version("phone-B", "13.2.0")
    c.present |= {("phone-A", "Connected"), ("phone-B", "Connected"), ("phone-B", "Allow")}
    from devicekit.extensions.devicekit_vpn import driver

    a = driver.connect("phone-A", location="US")
    b = driver.connect("phone-B", location="US")
    assert a["adapter"] == "12.x" and b["adapter"] == "13.x"
    # 13.x ran the extra consent step; 12.x did not.
    assert ("phone-B", "Allow") in c.taps and ("phone-A", "Allow") not in c.taps
    assert ("phone-A", "Connect") in c.taps


def test_connect_no_adapter_fails_loud(fresh_db):
    c = _client()
    c.set_version("dev-A", "14.5.0")                 # above supported range → not even in scope
    from devicekit.extensions.devicekit_vpn import driver
    with pytest.raises(devicekit_sdk.appdriver.AppVersionUnsupported):
        driver.connect("dev-A", location="US")
    assert c.taps == []                              # never tapped


# --------------------------------------------------------------------------- country allow-list
def test_connect_rejects_non_allowed_country(fresh_db):
    c = _client()                                    # allowed = US, CA
    c.set_version("dev-A", "12.4.0")
    from devicekit.extensions.devicekit_vpn import driver
    with pytest.raises(ValueError) as ei:
        driver.connect("dev-A", location="Germany - Frankfurt")
    assert "not in the allowed_countries" in str(ei.value)
    assert c.taps == []                              # rejected before touching the device


def test_country_code_resolution(fresh_db):
    c = _client()
    from devicekit.extensions.devicekit_vpn import driver
    assert driver.country_code("United States - New York") == "US"
    assert driver.country_code("uk") == "GB"
    assert driver.country_code("DE") == "DE"
    assert driver.country_code("Atlantis") == ""


# --------------------------------------------------------------------------- egress verification
def test_verify_egress_ok_when_country_allowed(fresh_db):
    c = _client()
    c.set_version("dev-A", "12.4.0")
    from devicekit.extensions.devicekit_vpn import driver
    res = driver.verify_egress("dev-A")
    assert res["ok"] is True and res["country"] == "US" and res["ip"] == "1.2.3.4"


def test_verify_egress_fails_on_wrong_country(fresh_db):
    c = _client()
    c.egress_json = '{"countryCode":"RU","query":"9.9.9.9"}'   # exit is Russia, not in allow-list
    c.set_version("dev-A", "12.4.0")
    from devicekit.extensions.devicekit_vpn import driver
    res = driver.verify_egress("dev-A")
    assert res["ok"] is False and res["country"] == "RU"
    # As an automation step it fails loud (would trigger the alert + screenshot).
    step = {"type": "vpn_verify_egress", "config": {}}
    with pytest.raises(Exception) as ei:
        c._execute_step(step, "dev-A")
    assert "Egress check failed" in str(ei.value)


def test_ensure_egress_remediates_then_reverifies(fresh_db):
    c = _client()
    c.set_version("dev-A", "12.4.0")
    c.present |= {("dev-A", "Connected")}
    from devicekit.extensions.devicekit_vpn import driver

    # First check wrong (RU), then a reconnect flips egress to an allowed country (US).
    calls = {"n": 0}
    real = c.run_adb_command

    def flaky(args, device=None):
        joined = args if isinstance(args, str) else " ".join(map(str, args))
        if "curl" in joined:
            calls["n"] += 1
            return ('{"countryCode":"RU","query":"9.9.9.9"}' if calls["n"] == 1
                    else '{"countryCode":"US","query":"1.2.3.4"}')
        return real(args, device)
    c.run_adb_command = flaky

    result = driver.ensure_egress("dev-A")
    assert result["remediated"] is True and result["country"] == "US"
    assert ("dev-A", "Connect") in c.taps            # it reconnected to remediate


# --------------------------------------------------------------------------- version policy
def test_over_ceiling_refuses_by_policy(fresh_db):
    c = _client(max_app_version="12")                # pin the whole fleet to the 12.x line
    c.set_version("dev-A", "13.1.0")                 # has an adapter, but exceeds the ceiling
    c.present |= {("dev-A", "Connected")}
    from devicekit.extensions.devicekit_vpn import driver
    with pytest.raises(devicekit_sdk.appdriver.VersionPolicyError):
        driver.connect("dev-A", location="US")
    assert c.taps == []


def test_reprovision_gated_off_by_default(fresh_db):
    c = _client()                                    # allow_reprovision not set
    from devicekit.extensions.devicekit_vpn import driver
    with pytest.raises(PermissionError):
        driver.reprovision("dev-A")


# --------------------------------------------------------------------------- registry (ph5)
@pytest.fixture
def _bundled_registry(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "")     # set-but-empty ⇒ bundled index only
    from devicekit import extension_registry
    extension_registry._reset_cache()
    yield
    extension_registry._reset_cache()


def test_vpn_registry_entry_carries_device_requirements(_bundled_registry):
    from devicekit import extension_registry
    entry = extension_registry.get_entry(SLUG)
    assert entry and entry["bundled"] is True and entry["first_party"] is True
    assert len(entry["sha256"]) == 64 and set(entry["sha256"]) != {"0"}
    assert entry["device_requirements"]["package"] == PKG


def test_vpn_installs_from_registry(fresh_db, _bundled_registry):
    c = _Host()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    devicekit_sdk.set_host(c)
    ext = c.install_extension_from_registry(SLUG)
    assert ext["status"] == "active"
    assert c._flask_app.test_client().get(f"/ext/{SLUG}/ping").status_code == 200
