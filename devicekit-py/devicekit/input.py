"""Input management: tap, swipe, key, text."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class InputManager:
    """Provides input methods: tap, swipe, text, key events."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def tap(self, x: int, y: int) -> dict:
        """Tap at coordinates (x, y)."""
        return self._conn.post_json("/input/tap", {"x": x, "y": y})

    def long_tap(self, x: int, y: int, duration: int = 1000) -> dict:
        """Long tap at coordinates (x, y)."""
        return self._conn.post_json("/input/long_tap", {"x": x, "y": y, "duration": duration})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> dict:
        """Swipe from (x1,y1) to (x2,y2)."""
        return self._conn.post_json("/input/swipe", {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration,
        })

    def text(self, text: str) -> dict:
        """Type text string."""
        return self._conn.post_json("/input/text", {"text": text})

    def key(self, keycode: str) -> dict:
        """Send a key event. Accepts KEYCODE_* names or numeric codes."""
        return self._conn.post_json("/input/key", {"keycode": keycode})

    def press(self, key: str) -> dict:
        """Press a named key: home, back, menu, recent, enter, delete, search,
        volume_up, volume_down, power."""
        keymap = {
            "home": "KEYCODE_HOME",
            "back": "KEYCODE_BACK",
            "menu": "KEYCODE_MENU",
            "recent": "KEYCODE_APP_SWITCH",
            "enter": "KEYCODE_ENTER",
            "delete": "KEYCODE_DEL",
            "search": "KEYCODE_SEARCH",
            "volume_up": "KEYCODE_VOLUME_UP",
            "volume_down": "KEYCODE_VOLUME_DOWN",
            "power": "KEYCODE_POWER",
        }
        keycode = keymap.get(key, key)
        return self.key(keycode)
