"""AI agent tool-call audit trail (plan 13).

Every write tool the per-device AI agent invokes passes through the ``ConfirmationGate``
and lands here as a row: what tool, what args, which session mode was active, how it was
decided (approved / denied / timeout / auto), who approved it, and the result. Read tools
are not gated and not audited — the point of the trail is accountability for actions that
touched real hardware. Extension-contributed write tools ride the same table.

Kept as its own table (not folded into ``DeviceCommand``) because a gate decision has its
own lifecycle fields (``mode``, ``decision``, ``approver``) that the command trail lacks.
"""
import uuid

from sqlalchemy import Column, String, Float, Boolean, JSON, Text

from devicekit.db import Base


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_log"

    # How the gate resolved the call.
    DECISION_APPROVED = "approved"    # a human approved a supervised gate
    DECISION_DENIED = "denied"        # a human denied it
    DECISION_TIMEOUT = "timeout"      # nobody answered before the deadline (default-deny)
    DECISION_AUTO = "auto"            # autonomous mode auto-approved (no human in the loop)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, index=True, nullable=False)
    tool = Column(String, nullable=False)
    args = Column(JSON, default=dict)
    is_write = Column(Boolean, default=True, nullable=False)
    category = Column(String, nullable=True)
    source = Column(String, nullable=True)      # core | extension:<slug> | self_heal
    mode = Column(String, nullable=True)        # observe | supervised | autonomous
    decision = Column(String, nullable=False, index=True)
    approver = Column(String, nullable=True)    # who approved/denied (api key holder / "system")
    result = Column(Text, nullable=True)        # tool result string (truncated) or refusal
    error = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, index=True)
    resolved_at = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "tool": self.tool,
            "args": self.args or {},
            "is_write": bool(self.is_write),
            "category": self.category,
            "source": self.source,
            "mode": self.mode,
            "decision": self.decision,
            "approver": self.approver,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "duration": (
                round(self.resolved_at - self.created_at, 3)
                if self.resolved_at and self.created_at else None
            ),
        }
