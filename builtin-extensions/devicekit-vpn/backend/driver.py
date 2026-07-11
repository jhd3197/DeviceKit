"""The VPN driver: turns extension config + adapters into concrete connect/disconnect/status/
provision/egress operations. Every device touch runs through the ``devicekit_sdk.appdriver``
framework (per-device adapter resolution, version policy) or the gated ``device_control`` seam.
"""
import re
import json

import devicekit_sdk
from devicekit_sdk import appdriver

from . import adapters

SLUG = "devicekit-vpn"
DEFAULT_PACKAGE = "com.expressvpn.vpn"
SUPPORTED_VERSIONS = ">=12.0.0 <14.0.0"      # mirrors device_requirements.supported_versions
DEFAULT_GEO_ENDPOINT = "http://ip-api.com/json"

log = devicekit_sdk.logger(SLUG)


# --------------------------------------------------------------------------- config accessors
def cfg():
    return devicekit_sdk.config(SLUG) or {}


def package():
    return (cfg().get("package") or "").strip() or DEFAULT_PACKAGE


def allowed_countries():
    """ISO codes the fleet may exit through. Empty list ⇒ no restriction."""
    raw = cfg().get("allowed_countries") or ""
    return [c.strip().upper() for c in re.split(r"[,\s]+", str(raw)) if c.strip()]


def preferred_location():
    return (cfg().get("preferred_location") or "").strip()


def _device_ceilings():
    raw = cfg().get("device_max_versions")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            log.warning("device_max_versions is not valid JSON — ignoring per-device ceilings")
    return {}


def ceiling_for(device_id):
    """Per-device ceiling wins, else the global ceiling; read fresh so operators can change it
    without a restart. Powers :class:`AppDriver`'s over-ceiling refusal (plan 18 Part 3)."""
    per = _device_ceilings()
    if per.get(device_id):
        return str(per[device_id])
    g = cfg().get("max_app_version")
    return str(g) if g else None


def build_driver():
    return appdriver.AppDriver(
        SLUG, package(), adapters.ADAPTERS,
        supported_versions=SUPPORTED_VERSIONS, ceiling_for=ceiling_for)


# --------------------------------------------------------------------------- country allow-list
# Light ISO-3166 alpha-2 alias table so a human-friendly location ("United States", "UK",
# "Germany - Frankfurt") can be checked against the allow-list. A location that is already a
# 2-letter code passes through. Unknown ⇒ empty (treated as not-allowed when a list is set).
_COUNTRY_ALIASES = {
    "united states": "US", "usa": "US", "us": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "england": "GB",
    "canada": "CA", "germany": "DE", "france": "FR", "netherlands": "NL",
    "japan": "JP", "australia": "AU", "singapore": "SG", "switzerland": "CH",
    "spain": "ES", "italy": "IT", "sweden": "SE", "brazil": "BR", "india": "IN",
    "mexico": "MX", "hong kong": "HK", "south korea": "KR", "korea": "KR",
}


def country_code(location):
    """Best-effort ISO alpha-2 for a location string (country code, country name, or
    'Country - City'). Returns '' when it can't resolve one."""
    s = (location or "").strip().lower()
    if not s:
        return ""
    head = re.split(r"[-(–—/,]", s)[0].strip()   # 'germany - frankfurt' -> 'germany'
    if head in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[head]
    if s in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[s]
    if re.fullmatch(r"[a-z]{2}", head):
        return head.upper()
    for name, code in _COUNTRY_ALIASES.items():
        if name in s:
            return code
    return ""


def validate_location(location):
    """Refuse a requested location whose country isn't in ``allowed_countries`` — the guardrail
    that keeps even the AI from routing to a non-approved exit. No-op when no allow-list is set."""
    allowed = allowed_countries()
    if not allowed or not location:
        return
    cc = country_code(location)
    if cc not in allowed and location.strip().upper() not in allowed:
        raise ValueError(
            f"location '{location}' resolves to country '{cc or '?'}', which is not in the "
            f"allowed_countries {allowed}")


# --------------------------------------------------------------------------- provisioning
def _apk_config():
    c = cfg()
    apk_b64 = c.get("apk_b64")
    if not apk_b64:
        raise appdriver.ProvisionError(
            "no APK configured — upload the ExpressVPN APK to the extension's apk_b64 config first")
    return apk_b64, c.get("apk_sha256"), (c.get("apk_version") or None)


def provision(device_id, serial=""):
    apk_b64, sha, ver = _apk_config()
    return appdriver.provision(
        SLUG, device_id, package=package(), apk_b64=apk_b64,
        expected_sha256=sha, expected_version=ver, serial=serial)


def reprovision(device_id, serial=""):
    """Gated + off by default: uninstall the drifted build and reinstall the pin (a downgrade)."""
    if not cfg().get("allow_reprovision"):
        raise PermissionError(
            "reprovision is disabled — it uninstalls + reinstalls the app; set "
            "allow_reprovision=true in the extension config to enable it")
    apk_b64, sha, ver = _apk_config()
    return appdriver.reprovision(
        SLUG, device_id, package=package(), apk_b64=apk_b64,
        expected_sha256=sha, expected_version=ver, serial=serial)


def provisioned():
    return appdriver.list_provisions(SLUG)


# --------------------------------------------------------------------------- flows
def connect(device_id, location=None):
    """Connect ``device_id`` to ``location`` (or the preferred location), validating the country
    first. Resolves the right connect adapter for the device's installed version (plan 18)."""
    loc = (location or preferred_location() or "").strip()
    validate_location(loc)
    result = build_driver().run("connect", device_id, variables={"location": loc} if loc else {})
    result["location"] = loc
    return result


def disconnect(device_id):
    return build_driver().run("disconnect", device_id)


def status(device_id):
    result = build_driver().run("status", device_id)
    return {
        "device_id": device_id, "version": result["version"],
        "connected": result["vars"].get("connected"),
        "status": result["vars"].get("status"),
    }


# --------------------------------------------------------------------------- egress verification
def _parse_geo(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {}


def verify_egress(device_id, expected_country=None):
    """Confirm the *real* exit country by having the device fetch its own public IP + geo — the
    app UI can't reveal a wrong-country connection, so this is the only honest check. Compares the
    exit country to ``expected_country`` (or, if absent, the allow-list). Returns a dict with
    ``ok``; raises nothing (the step type decides whether a mismatch fails the run)."""
    endpoint = (cfg().get("geo_endpoint") or DEFAULT_GEO_ENDPOINT).strip()
    control = devicekit_sdk.device_control(SLUG, device_id)
    raw = control.shell(f"curl -s {endpoint}") or ""
    data = _parse_geo(raw)
    country = str(data.get("countryCode") or data.get("country_code") or "").upper()
    ip = str(data.get("query") or data.get("ip") or "")
    allowed = allowed_countries()
    expected = (expected_country or "").strip().upper()
    if expected:
        ok = country == expected
    elif allowed:
        ok = country in allowed
    else:
        ok = bool(country)          # no policy set: just confirm we resolved a country at all
    return {
        "device_id": device_id, "ip": ip, "country": country, "ok": ok,
        "expected": expected or (",".join(allowed) if allowed else "any"),
        "raw": raw[:400],
    }


def ensure_egress(device_id):
    """The steady-state remediation loop as one step: verify egress → if wrong, reconnect to the
    preferred location → re-verify. Raises :class:`AppDriverError` if it still can't reach an
    approved country, so the automation fails loud and the notification bus alerts (plan 18 says:
    wrong adapter/version → alert, don't tap — that propagates from the driver as a step failure)."""
    first = verify_egress(device_id)
    if first["ok"]:
        return {"remediated": False, **first}
    log.warning(
        f"VPN egress on {device_id} is '{first['country'] or '?'}' (want {first['expected']}) — "
        f"reconnecting to preferred location")
    connect(device_id)                                  # to preferred_location, country-validated
    second = verify_egress(device_id)
    if not second["ok"]:
        raise appdriver.AppDriverError(
            f"VPN egress on {device_id} is still '{second['country'] or '?'}' after reconnect "
            f"(want {second['expected']})")
    return {"remediated": True, "before": first, **second}
