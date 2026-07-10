"""Device command audit trail (plan 07).

Every command dispatched to an on-device agent is persisted as a row moving through a
stable lifecycle (``pending → running → completed | failed | timeout``). This gives the UI
a "device action history" panel for free and makes synchronous dispatch (block the caller
on a ``queue.Queue`` until the agent posts a result) durable and queryable — the ServerKit
``send_command()`` pattern ported to Android device agents.
"""
import uuid

from sqlalchemy import Column, String, Float, JSON, Text

from devicekit.db import Base


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"

    TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED, STATUS_TIMEOUT)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, index=True, nullable=False)
    command = Column(String, nullable=False)
    args = Column(JSON, default=dict)
    status = Column(String, default=STATUS_PENDING, nullable=False, index=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    source = Column(String, nullable=True)  # who dispatched (api / automation / ...)
    created_at = Column(Float, nullable=False)
    started_at = Column(Float, nullable=True)
    completed_at = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "command": self.command,
            "args": self.args or {},
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "source": self.source,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": (
                round(self.completed_at - self.started_at, 3)
                if self.completed_at and self.started_at else None
            ),
        }
