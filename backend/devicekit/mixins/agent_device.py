"""On-device agent registry: live in-memory cache + persistence helpers.

The live registry (``_agent_device_states`` and friends) is an in-memory cache for fast
SSE fan-out and heartbeat tracking, backed by AgentDevice rows so registered devices
survive a restart. The event ring buffer remains ephemeral. Plan 02 lifted this registry
out of the ``api_app()`` closure onto the client; plan 07 (Agent Device Platform) builds
on it further.
"""
import time
import logging

from devicekit.db import session_scope
from devicekit.models import AgentDevice

logger = logging.getLogger(__name__)


class AgentDeviceMixin:
    """Live agent-device registry + DB read/write helpers."""

    # -----------------------------------------------------------
    # Live registry (in-memory cache, hydrated from DB at boot)
    # -----------------------------------------------------------
    def init_agent_registry(self):
        """Create the in-memory registry and hydrate it from persisted rows.

        Called once from ``Client.__init__`` after persistence is up. Idempotent.
        """
        self._agent_device_states = {}
        self._agent_device_events = []
        self._agent_device_serial_index = {}  # serial -> device_id mapping
        try:
            for row in self.load_agent_devices():
                did = row['device_id']
                serial = row.pop('serial', None)
                self._agent_device_states[did] = {
                    'device_id': did,
                    'info': row.get('info', {}),
                    'registered_at': row.get('registered_at'),
                    'last_heartbeat': row.get('last_heartbeat'),
                    'state': row.get('state', {}),
                    'online': row.get('online', False),
                }
                if serial:
                    self._agent_device_serial_index[serial] = did
            if self._agent_device_states:
                logger.info(
                    f"Loaded {len(self._agent_device_states)} persisted agent device(s)"
                )
        except Exception as e:
            logger.warning(f"Could not load persisted agent devices: {e}")

    def _ensure_agent_registry(self):
        # Safety net if a code path reaches the registry before init_agent_registry().
        if not hasattr(self, '_agent_device_states'):
            self.init_agent_registry()

    def find_agent_device(self, device_id):
        """Find agent device state by device_id or serial-number cross-reference."""
        self._ensure_agent_registry()
        # Direct lookup
        if device_id in self._agent_device_states:
            return self._agent_device_states[device_id]
        # Try serial number index (ADB device IDs may be serial numbers)
        if device_id in self._agent_device_serial_index:
            mapped_id = self._agent_device_serial_index[device_id]
            return self._agent_device_states.get(mapped_id)
        # Fuzzy match: check if device_id is a substring of any agent device ID
        for agent_id, state in self._agent_device_states.items():
            if device_id in agent_id or agent_id in device_id:
                return state
            # Check serial in info
            info = state.get('info', {})
            if info.get('serial') == device_id:
                return state
        return None

    # -----------------------------------------------------------
    # Persistence helpers
    # -----------------------------------------------------------
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
