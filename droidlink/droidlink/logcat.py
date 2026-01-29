"""Logcat access: dump and stream."""

import json
import threading
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class LogcatStream:
    """
    Stream logcat output in real-time.

    Usage:
        stream = d.logcat.stream(filter="MyApp")
        stream.on_line(lambda line: print(line))
        stream.start()
        # ... later
        stream.stop()
    """

    def __init__(self, conn: "Connection", filter: str = "", level: str = ""):
        self._conn = conn
        self._filter = filter
        self._level = level
        self._handler: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def on_line(self, handler: Callable) -> "LogcatStream":
        """Register a handler for each logcat line."""
        self._handler = handler
        return self

    def start(self) -> "LogcatStream":
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _listen(self):
        try:
            params = {}
            if self._filter:
                params["filter"] = self._filter
            if self._level:
                params["level"] = self._level

            resp = self._conn.get("/logcat/stream", params=params, stream=True, timeout=None)
            for line in resp.iter_lines(decode_unicode=True):
                if not self._running:
                    break
                if line and line.startswith("data:"):
                    log_line = line[5:].strip()
                    if self._handler:
                        self._handler(log_line)
        except Exception:
            pass
        finally:
            self._running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class LogcatManager:
    """
    Access device logcat.

    Usage:
        lines = d.logcat.dump(lines=50, filter="MyApp")
        d.logcat.clear()

        # Stream
        stream = d.logcat.stream(filter="Error")
        stream.on_line(print)
        stream.start()
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def dump(self, lines: int = 100, filter: str = "", level: str = "") -> List[str]:
        """Dump recent logcat lines."""
        params = {"lines": lines}
        if filter:
            params["filter"] = filter
        if level:
            params["level"] = level
        data = self._conn.get_json("/logcat", params=params)
        return data.get("lines", [])

    def clear(self) -> dict:
        """Clear logcat buffer."""
        return self._conn.post_json("/logcat/clear")

    def stream(self, filter: str = "", level: str = "") -> LogcatStream:
        """Create a live logcat stream."""
        return LogcatStream(self._conn, filter=filter, level=level)
