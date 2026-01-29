"""Clipboard management."""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class ClipboardManager:
    """Get/set device clipboard."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def get(self) -> Optional[str]:
        """Get clipboard text."""
        data = self._conn.get_json("/clipboard")
        return data.get("text")

    def set(self, text: str) -> dict:
        """Set clipboard text."""
        return self._conn.post_json("/clipboard", {"text": text})
