"""Gesture recording and replay."""

from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class GestureManager:
    """
    Record and replay gesture sequences.

    Usage:
        # Record a gesture
        d.gestures.start_recording()
        d.gestures.record_tap(500, 800)
        d.gestures.record_wait(1000)
        d.gestures.record_swipe(500, 800, 500, 200, 300)
        d.gestures.stop_recording("my_gesture")

        # Replay it
        d.gestures.replay("my_gesture")
        d.gestures.replay("my_gesture", times=5)

        # List saved gestures
        for g in d.gestures.list():
            print(g["name"], g["event_count"])
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def start_recording(self) -> dict:
        """Start recording a gesture sequence."""
        return self._conn.post_json("/gesture/record/start")

    def record_tap(self, x: int, y: int) -> dict:
        """Record a tap event at (x, y)."""
        return self._conn.post_json("/gesture/record/tap", {"x": x, "y": y})

    def record_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> dict:
        """Record a swipe event."""
        return self._conn.post_json("/gesture/record/swipe", {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration,
        })

    def record_key(self, keycode: str) -> dict:
        """Record a key press event."""
        return self._conn.post_json("/gesture/record/key", {"keycode": keycode})

    def record_wait(self, ms: int = 1000) -> dict:
        """Record a wait/pause event."""
        return self._conn.post_json("/gesture/record/wait", {"ms": ms})

    def stop_recording(self, name: str) -> dict:
        """Stop recording and save the gesture with a name."""
        return self._conn.post_json("/gesture/record/stop", {"name": name})

    def replay(self, name: str = "", times: int = 1, events: Optional[list] = None) -> dict:
        """
        Replay a saved gesture or inline events.

        Args:
            name: Name of saved gesture to replay.
            times: Number of times to replay.
            events: Optional list of inline events (if name is empty).
        """
        body = {"times": times}
        if name:
            body["name"] = name
        if events:
            body["events"] = events
        return self._conn.post_json("/gesture/replay", body)

    def list(self) -> List[dict]:
        """List all saved gestures."""
        data = self._conn.get_json("/gesture/list")
        return data.get("gestures", [])

    def get(self, name: str) -> dict:
        """Get a saved gesture by name."""
        return self._conn.get_json("/gesture/get", params={"name": name})

    def delete(self, name: str) -> dict:
        """Delete a saved gesture."""
        return self._conn.post_json("/gesture/delete", {"name": name})
