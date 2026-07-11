"""Automation step types for devicekit-vpn. The AutomationEditor renders each step's config form
from this registry — no frontend code needed. Every step delegates to :mod:`driver`, so an
unsupported version / missing adapter / over-ceiling device raises and *fails the step loud*
(triggering screenshot-on-failure + the automation.run.failed notification) rather than tapping.

``vpn_status`` supports ``store_as`` so its result lands in a run variable for later steps.
"""
from . import driver

SLUG = "devicekit-vpn"


def _provision(client, config, device_id):
    rec = driver.provision(device_id, serial=config.get("serial", ""))
    if rec.get("status") == "version_mismatch":
        raise Exception(
            f"Provisioned {rec['package']} but versionName is {rec['version_name']} "
            f"(expected the pinned build) — check apk_version/apk_sha256")
    return f"Provisioned {rec['package']} v{rec['version_name']} ({rec['status']})"


def _reprovision(client, config, device_id):
    rec = driver.reprovision(device_id, serial=config.get("serial", ""))
    return f"Reprovisioned {rec['package']} v{rec['version_name']} ({rec['status']})"


def _connect(client, config, device_id):
    result = driver.connect(device_id, location=config.get("location") or None)
    return f"Connected via {result['adapter']} adapter (v{result['version']}, location='{result['location']}')"


def _disconnect(client, config, device_id):
    result = driver.disconnect(device_id)
    return f"Disconnected via {result['adapter']} adapter (v{result['version']})"


def _status(client, config, device_id):
    st = driver.status(device_id)
    return st


def _verify_egress(client, config, device_id):
    result = driver.verify_egress(device_id, expected_country=config.get("expected_country") or None)
    if not result["ok"]:
        raise Exception(
            f"Egress check failed: exiting via '{result['country'] or '?'}' "
            f"(want {result['expected']}), ip={result['ip'] or '?'}")
    return f"Egress OK: {result['country']} (ip {result['ip']})"


def _ensure_egress(client, config, device_id):
    result = driver.ensure_egress(device_id)
    if result.get("remediated"):
        return f"Egress remediated → {result['country']} (was {result['before']['country'] or '?'})"
    return f"Egress OK: {result['country']} (no remediation needed)"


def register():
    return {
        "vpn_provision": {
            "label": "VPN: Provision app",
            "category": "VPN",
            "config": {
                "serial": {"type": "text", "label": "Device serial (recorded)", "required": False},
            },
            "execute": _provision,
        },
        "vpn_reprovision": {
            "label": "VPN: Reprovision (downgrade to pin)",
            "category": "VPN",
            "config": {
                "serial": {"type": "text", "label": "Device serial (recorded)", "required": False},
            },
            "execute": _reprovision,
        },
        "vpn_connect": {
            "label": "VPN: Connect",
            "category": "VPN",
            "config": {
                "location": {"type": "text", "label": "Location (blank = preferred)", "required": False},
            },
            "execute": _connect,
        },
        "vpn_disconnect": {
            "label": "VPN: Disconnect",
            "category": "VPN",
            "config": {},
            "execute": _disconnect,
        },
        "vpn_status": {
            "label": "VPN: Status",
            "category": "VPN",
            "config": {
                "store_as": {"type": "text", "label": "Store result as variable", "required": False},
            },
            "execute": _status,
        },
        "vpn_verify_egress": {
            "label": "VPN: Verify egress country",
            "category": "VPN",
            "config": {
                "expected_country": {"type": "text", "label": "Expected country (blank = allow-list)", "required": False},
            },
            "execute": _verify_egress,
        },
        "vpn_ensure_egress": {
            "label": "VPN: Ensure egress (verify + self-heal)",
            "category": "VPN",
            "config": {},
            "execute": _ensure_egress,
        },
    }
