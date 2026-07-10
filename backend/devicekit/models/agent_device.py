"""Registered agent-device model.

Persists the ``_agent_device_states`` registry that used to live only in an ``api_app()``
closure, so devices that registered via the on-device agent survive a restart. The live
event ring buffer and heartbeat-driven online flag remain ephemeral. Coordinates with
plan 07 (Agent Device Platform).
"""
from sqlalchemy import Column, String, Float, Boolean, JSON

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

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "info": self.info or {},
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "state": self.state or {},
            "online": bool(self.online),
        }
