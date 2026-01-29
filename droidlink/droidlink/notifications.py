"""Notification management (unique feature)."""

from typing import List, TYPE_CHECKING
from .types import NotificationInfo

if TYPE_CHECKING:
    from .connection import Connection


class NotificationManager:
    """Access device notifications via NotificationAgent."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def list(self) -> List[NotificationInfo]:
        """List recent notifications."""
        data = self._conn.get_json("/notifications")
        return [NotificationInfo.from_dict(n) for n in data.get("notifications", [])]

    def clear(self) -> dict:
        """Clear the notification buffer."""
        return self._conn.post_json("/notifications/clear")
