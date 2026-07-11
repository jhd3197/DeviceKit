"""AI tools for devicekit-browser — bound namespaced ``devicekit_browser__*`` into every
per-device Prompture ToolRegistry.

Per-device tools declare a ``device_id`` parameter; the host binds it to the conversation's
device and hides it from the model. Write tools (``goto``, ``evaluate``, ``fetch_url``) are
always routed through the confirmation gate (plan 13); read tools run free.
"""
import base64

import devicekit_sdk

from . import cdp, sessions, pools

SLUG = "devicekit-browser"


def register(ai):
    @ai.tool
    def goto(url: str, device_id: str = "") -> str:
        """Open a URL in the device's Chrome and wait for it to load. Returns the final URL."""
        port, tid = sessions.session_context(device_id)
        return cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())

    @ai.tool
    def evaluate(expression: str, device_id: str = "") -> str:
        """Evaluate a JavaScript expression in the device's current page and return its value."""
        port, tid = sessions.session_context(device_id)
        return str(cdp.evaluate(port, tid, expression, timeout=sessions.cdp_timeout()))

    @ai.tool(is_write=False)
    def get_content(device_id: str = "", format: str = "text") -> str:
        """Read the current page as 'text', 'html', or 'title' (default text)."""
        port, tid = sessions.session_context(device_id)
        return str(cdp.content(port, tid, fmt=format, timeout=sessions.cdp_timeout()) or "")[:20000]

    @ai.tool(is_write=False)
    def get_url(device_id: str = "") -> str:
        """Return the URL of the device's current page."""
        port, tid = sessions.session_context(device_id)
        return str(cdp.content(port, tid, fmt="url", timeout=sessions.cdp_timeout()) or "")

    @ai.tool(is_write=False)
    def screenshot(device_id: str = "") -> str:
        """Capture the current page and return it as a base64 PNG data URI."""
        port, tid = sessions.session_context(device_id)
        png = cdp.screenshot(port, tid, timeout=sessions.cdp_timeout())
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    @ai.tool
    def fetch_url(url: str, pool: str = "default", format: str = "text") -> str:
        """Fetch a URL through a device pool (round-robin across the fleet). Returns the page
        content prefixed with which device served it."""
        pool_row = pools.get_pool(pool)
        if not pool_row:
            return f"No such pool '{pool}'. Create one first."
        excluded = set()
        members = pools.resolve_members(pool_row)
        last_err = None
        for _ in range(max(1, len(members))):
            device_id = pools.pick_device(pool_row, exclude=excluded)
            try:
                port, tid = sessions.session_context(device_id)
                cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())
                body = cdp.content(port, tid, fmt=format, timeout=sessions.cdp_timeout())
                return f"[served by {device_id}]\n{str(body or '')[:20000]}"
            except cdp.CDPError as e:
                last_err = e
                pools.mark_unhealthy(device_id)
                excluded.add(device_id)
        return f"Fetch failed across pool '{pool}': {last_err}"
