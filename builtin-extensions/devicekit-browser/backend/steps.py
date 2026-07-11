"""Automation step types for devicekit-browser. The AutomationEditor renders each step's
config form from this registry, so no frontend code is needed.

``browser_evaluate`` supports ``store_as`` — its result lands in a run variable so a later
step can reference it as ``{{name}}``.
"""
from . import cdp, sessions

SLUG = "devicekit-browser"


def _goto(client, config, device_id):
    url = config.get("url")
    if not url:
        raise ValueError("url is required")
    port, tid = sessions.session_context(device_id)
    final = cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())
    return f"Navigated to {final}"


def _assert_text(client, config, device_id):
    text = config.get("text") or ""
    if not text:
        raise ValueError("text is required")
    port, tid = sessions.session_context(device_id)
    if config.get("url"):
        cdp.navigate(port, tid, config["url"], timeout=sessions.cdp_timeout())
    body = cdp.content(port, tid, fmt="text", timeout=sessions.cdp_timeout()) or ""
    if text not in body:
        raise Exception(f"Assertion failed: '{text}' not found on page")
    return f"Found '{text}'"


def _evaluate(client, config, device_id):
    expression = config.get("expression")
    if not expression:
        raise ValueError("expression is required")
    port, tid = sessions.session_context(device_id)
    return cdp.evaluate(port, tid, expression, timeout=sessions.cdp_timeout())


def _screenshot(client, config, device_id):
    port, tid = sessions.session_context(device_id)
    full = bool(config.get("full"))
    png = cdp.screenshot(port, tid, full_page=full, timeout=sessions.cdp_timeout())
    return f"Captured screenshot ({len(png)} bytes)"


def register():
    return {
        "browser_goto": {
            "label": "Browser: Navigate",
            "category": "Browser",
            "config": {
                "url": {"type": "text", "label": "URL", "required": True},
            },
            "execute": _goto,
        },
        "browser_assert_text": {
            "label": "Browser: Assert Text",
            "category": "Browser",
            "config": {
                "text": {"type": "text", "label": "Text must be present", "required": True},
                "url": {"type": "text", "label": "URL (optional — navigate first)", "required": False},
            },
            "execute": _assert_text,
        },
        "browser_evaluate": {
            "label": "Browser: Evaluate JS",
            "category": "Browser",
            "config": {
                "expression": {"type": "text", "label": "JavaScript expression", "required": True},
                "store_as": {"type": "text", "label": "Store result as variable", "required": False},
            },
            "execute": _evaluate,
        },
        "browser_screenshot": {
            "label": "Browser: Screenshot",
            "category": "Browser",
            "config": {
                "full": {"type": "boolean", "label": "Full page", "required": False},
            },
            "execute": _screenshot,
        },
    }
