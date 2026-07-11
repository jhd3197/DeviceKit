"""Server-Sent Events broadcast infrastructure.

Real-time in DeviceKit is SSE (no Socket.IO/WebSockets). This mixin owns the connected
client registry and the fan-out helper. It used to live as a closure inside
``api_app()``; lifting it onto the client lets any mixin push events
(``self.broadcast(...)``) and lets the ``events`` blueprint own only the HTTP route.
"""
import json
import queue
import threading


class EventsMixin:
    """SSE client registry + broadcast helper, shared across the app."""

    def _ensure_sse(self):
        # Lazy init so the mixin needs no cooperative __init__. Single-process app,
        # so a plain list + lock is enough.
        if not hasattr(self, '_sse_clients'):
            self._sse_clients = []
            self._sse_lock = threading.Lock()

    def broadcast(self, event_type, data):
        """Push an event to all connected SSE clients."""
        self._ensure_sse()
        msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        with self._sse_lock:
            dead = []
            for q in self._sse_clients:
                try:
                    q.put_nowait(msg)
                except Exception:
                    dead.append(q)
            for q in dead:
                self._sse_clients.remove(q)

    def sse_stream(self):
        """Register a new client queue and return an SSE generator for it."""
        self._ensure_sse()
        client_queue = queue.Queue(maxsize=100)
        with self._sse_lock:
            self._sse_clients.append(client_queue)

        def _gen():
            try:
                yield "event: connected\ndata: {}\n\n"
                while True:
                    try:
                        yield client_queue.get(timeout=15)
                    except queue.Empty:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                with self._sse_lock:
                    if client_queue in self._sse_clients:
                        self._sse_clients.remove(client_queue)

        return _gen()
