"""Automation step type ``wait_for_notification`` — the killer primitive: block for a device
notification matching a regex, extract the first capture group into a run variable.

Pair it with ``store_as`` to turn "log into app X" into a five-step automation:
``open_app`` -> ``type_text`` (credentials) -> ``wait_for_notification`` (``(\\d{6})`` from the
SMS app, ``store_as: otp``) -> ``type_text`` (``{{otp}}``).
"""
from . import capture


def _wait_for_notification(client, config, device_id):
    pattern = config.get("pattern")
    if not pattern:
        raise ValueError("pattern is required")
    package = config.get("package") or None
    try:
        timeout = int(config.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60
    result = capture.wait_for_match(device_id, pattern, package=package, timeout=timeout)
    if result is None:
        raise Exception(f"No notification matched {pattern!r} within {timeout}s")
    return result


def register():
    return {
        "wait_for_notification": {
            "label": "Wait for Notification",
            "category": "Notification",
            "config": {
                "package": {"type": "text", "label": "Package (optional filter)", "required": False},
                "pattern": {"type": "text", "label": "Regex (first group → variable)", "required": True},
                "timeout": {"type": "number", "label": "Timeout (seconds)", "required": False, "default": 60},
                "store_as": {"type": "text", "label": "Store result as variable", "required": False},
            },
            "execute": _wait_for_notification,
        }
    }
