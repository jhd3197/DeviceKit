"""Device metrics management (unique feature)."""

from typing import List, TYPE_CHECKING
from .types import MetricsSnapshot

if TYPE_CHECKING:
    from .connection import Connection


class MetricsManager:
    """Access live device metrics via MetricsCollector."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def snapshot(self) -> MetricsSnapshot:
        """Get the latest metrics snapshot."""
        data = self._conn.get_json("/metrics")
        return MetricsSnapshot.from_dict(data)

    def history(self) -> List[MetricsSnapshot]:
        """Get metrics history (up to 60 entries, 2s intervals)."""
        data = self._conn.get_json("/metrics/history")
        return [MetricsSnapshot.from_dict(m) for m in data.get("history", [])]
