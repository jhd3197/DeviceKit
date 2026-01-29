"""Screen management: screenshot, rotation, wake/sleep."""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class ScreenManager:
    """Screenshot, rotation, wake/sleep controls."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def screenshot(self, filename: Optional[str] = None) -> bytes:
        """Take a screenshot. Returns PNG bytes. Optionally saves to file."""
        data = self._conn.get_bytes("/screen/shot", timeout=15)
        if filename:
            Path(filename).write_bytes(data)
        return data

    @property
    def rotation(self) -> int:
        """Get current screen rotation (0, 1, 2, 3)."""
        return self._conn.get_json("/screen/rotation").get("rotation", 0)

    def wake(self) -> dict:
        """Wake the screen."""
        return self._conn.post_json("/screen/wake")

    def sleep(self) -> dict:
        """Put the screen to sleep."""
        return self._conn.post_json("/screen/sleep")
