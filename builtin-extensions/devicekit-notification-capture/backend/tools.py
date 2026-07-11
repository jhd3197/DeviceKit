"""AI tools for devicekit-notification-capture — bound namespaced
``devicekit_notification_capture__*``. Both are read tools (they mutate nothing on the
device; ``wait_for_notification`` merely blocks with a bounded timeout).

Also registers the plan-06 catalog event this extension forwards onto the bus. Registration
happens during activation (``_current_slug`` is set), so it is tracked and torn down on
disable/uninstall.
"""
import devicekit_sdk

from . import capture


def register(ai):
    # Catalog entry for bus forwarding (data keys interpolate into title/body).
    devicekit_sdk.notify.register_event(
        capture.CAPTURED_EVENT,
        "{package}: {title}",
        severity="info", category="monitoring",
        body="{text}", deep_link="")

    @ai.tool(is_write=False)
    def recent_notifications(limit: int = 20, device_id: str = "") -> str:
        """List recently captured device notifications (package, title, text)."""
        items = capture.recent(device_id=device_id or None, limit=min(int(limit or 20), 100))
        if not items:
            return "(no captured notifications)"
        return "\n".join(f"[{i['package']}] {i['title']}: {i['text']}"[:200] for i in items)

    @ai.tool(is_write=False)
    def wait_for_notification(pattern: str, package: str = "", timeout: int = 60,
                              device_id: str = "") -> str:
        """Block up to `timeout` seconds for a new device notification matching `pattern`
        (regex). Returns the first capture group — e.g. an OTP code — or empty on timeout."""
        result = capture.wait_for_match(
            device_id, pattern, package=package or None, timeout=int(timeout or 60))
        return result if result is not None else ""
