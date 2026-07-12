"""User-attributed audit log (plan 20, part 3).

The durable, identity-attributed trail that hangs DeviceKit's audit-shaped events off real
principals. Distinct from ``AgentAuditLog`` (which keeps its own gate-decision lifecycle) and from
``ActivityMixin``'s in-memory feed (kept for the live ``/activities`` view). ``username`` /
``principal_kind`` are snapshotted so a row stays legible after the user is deleted.
"""
import time
import uuid

from sqlalchemy import Column, String, Float, Integer, JSON

from devicekit.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    action = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True)            # snapshot for display
    principal_kind = Column(String, nullable=True)      # solo | user | apikey | legacy | agent
    target_type = Column(String, nullable=True, index=True)
    target_id = Column(String, nullable=True, index=True)
    details = Column(JSON, default=dict)                # redacted before persist
    status = Column(Integer, nullable=True)             # HTTP status when audit-ing a request
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "user_id": self.user_id,
            "username": self.username,
            "principal_kind": self.principal_kind,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details or {},
            "status": self.status,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
        }
