"""Persistence helpers for the on-device agent registry.

The live registry (``_agent_device_states`` and friends) stays an in-memory cache inside
``api_app()`` for fast SSE fan-out and heartbeat tracking, but it is now backed by
AgentDevice rows so registered devices survive a restart. The event ring buffer remains
ephemeral. Coordinates with plan 07 (Agent Device Platform), which will lift the registry
out of the closure entirely.
"""
import time
import logging

from devicekit.db import session_scope
from devicekit.models import AgentDevice

logger = logging.getLogger(__name__)


class AgentDeviceMixin:
    """DB read/write helpers for registered agent devices."""

    def load_agent_devices(self):
        """Return all persisted agent-device rows as dicts (with serial for indexing)."""
        with session_scope() as s:
            out = []
            for row in s.query(AgentDevice).all():
                d = row.to_dict()
                d["serial"] = row.serial
                out.append(d)
            return out

    def save_agent_device(self, device_id, info, serial=None, registered_at=None,
                          last_heartbeat=None, state=None, online=True):
        """Upsert an agent device (used on registration)."""
        now = time.time()
        with session_scope() as s:
            row = s.get(AgentDevice, device_id)
            if not row:
                row = AgentDevice(device_id=device_id, registered_at=registered_at or now)
                s.add(row)
            row.info = info or {}
            row.serial = serial
            row.state = state or {}
            row.last_heartbeat = last_heartbeat if last_heartbeat is not None else now
            row.online = online

    def update_agent_device_fields(self, device_id, **fields):
        """Partial update of a persisted agent device (state, last_heartbeat, online)."""
        with session_scope() as s:
            row = s.get(AgentDevice, device_id)
            if not row:
                return False
            for key in ("info", "state", "last_heartbeat", "online", "serial"):
                if key in fields:
                    setattr(row, key, fields[key])
            return True
