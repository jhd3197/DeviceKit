"""Real-time event streaming via Server-Sent Events (SSE)."""

import json
import threading
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class EventStream:
    """
    Subscribe to real-time device events via SSE.

    Usage:
        stream = d.events.stream()
        stream.on("notification", lambda data: print(f"Notification: {data['title']}"))
        stream.on("keyboard", lambda data: print(f"Keyboard visible: {data['visible']}"))
        stream.on("window", lambda data: print(f"App: {data['package']}"))
        stream.on("metrics", lambda data: print(f"CPU: {data['cpu_percent']}%"))
        stream.start()
        # ... later
        stream.stop()

    Or as a context manager:
        with d.events.stream() as stream:
            stream.on("notification", handler)
            stream.wait()
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn
        self._handlers: dict[str, list[Callable]] = {}
        self._all_handler: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def on(self, event_type: str, handler: Callable) -> "EventStream":
        """Register a handler for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        return self

    def on_any(self, handler: Callable) -> "EventStream":
        """Register a handler for all events."""
        self._all_handler = handler
        return self

    def start(self) -> "EventStream":
        """Start listening for events in a background thread."""
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """Stop listening for events."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def wait(self):
        """Block until the stream is stopped."""
        if self._thread:
            try:
                while self._running:
                    self._thread.join(timeout=1)
            except KeyboardInterrupt:
                self.stop()

    def _listen(self):
        """Internal: connect to SSE endpoint and dispatch events."""
        try:
            resp = self._conn.get("/events/stream", stream=True, timeout=None)
            event_type = None
            for line in resp.iter_lines(decode_unicode=True):
                if not self._running:
                    break
                if line is None:
                    continue
                line = line.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        data = {"raw": data_str}

                    self._dispatch(event_type or "message", data)
                    event_type = None
                elif line.startswith(":"):
                    # Comment / keepalive, ignore
                    pass
        except Exception:
            if self._running:
                pass  # Connection lost
        finally:
            self._running = False

    def _dispatch(self, event_type: str, data: dict):
        """Dispatch event to registered handlers."""
        if self._all_handler:
            try:
                self._all_handler(event_type, data)
            except Exception:
                pass

        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        """Get number of connected SSE clients on the device."""
        data = self._conn.get_json("/events/clients")
        return data.get("count", 0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class EventManager:
    """Access to event streaming. Usage: d.events.stream()"""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def stream(self) -> EventStream:
        """Create a new event stream."""
        return EventStream(self._conn)

    @property
    def client_count(self) -> int:
        """Get number of connected SSE clients."""
        data = self._conn.get_json("/events/clients")
        return data.get("count", 0)
