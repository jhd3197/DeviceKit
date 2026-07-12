"""Registered agent-device model.

Persists the ``_agent_device_states`` registry that used to live only in an ``api_app()``
closure, so devices that registered via the on-device agent survive a restart. The live
event ring buffer and heartbeat-driven online flag remain ephemeral. Coordinates with
plan 07 (Agent Security & Fleet Registry): carries the per-device HMAC ``secret`` issued at
enrollment (plus pending-secret columns for zero-downtime key rotation), the advertised
``capabilities`` map, and the last source IP for anomaly logging.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, JSON

from devicekit.db import Base


class AgentDevice(Base):
    __tablename__ = "agent_devices"

    device_id = Column(String, primary_key=True)
    serial = Column(String, index=True, nullable=True)
    info = Column(JSON, default=dict)
    state = Column(JSON, default=dict)
    registered_at = Column(Float, nullable=False)
    last_heartbeat = Column(Float, nullable=True)
    online = Column(Boolean, default=True)

    # --- plan 07: HMAC auth + key rotation ---
    secret = Column(String, nullable=True)              # active per-device HMAC secret
    secret_pending = Column(String, nullable=True)      # staged next secret during rotation
    secret_rotated_at = Column(Float, nullable=True)    # when rotation was started

    # --- plan 07: capability advertisement ---
    capabilities = Column(JSON, default=dict)           # {screen_record: true, android_api: 34, ...}

    # --- plan 25 part 2: version negotiation (which agent version is on which device) ---
    agent_version = Column(String, nullable=True)       # advertised versionName, e.g. "1.2.0"
    agent_version_code = Column(Integer, nullable=True)  # advertised versionCode, e.g. 5

    # --- plan 07: anomaly logging ---
    last_ip = Column(String, nullable=True)

    # --- plan 20 part 4: born-in-workspace. NULL = global (unscoped). ---
    workspace_id = Column(String, nullable=True, index=True)

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "info": self.info or {},
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "state": self.state or {},
            "online": bool(self.online),
            "capabilities": self.capabilities or {},
            "agent_version": self.agent_version,
            "agent_version_code": self.agent_version_code,
            "enrolled": bool(self.secret),
            "rotating_key": bool(self.secret_pending),
            "last_ip": self.last_ip,
            "workspace_id": self.workspace_id,
        }
