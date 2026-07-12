"""An OTA rollout of a release across the fleet (plan 25 part 3).

Carries the rollout *policy* (``config``) and its live position (``stage`` +
``stage_entered_at``). The scheduled ``ota.rollout.advance`` job drives it canary → staged →
full → completed, or flips it to ``rolled_back`` when the failure rate crosses the
threshold. ``rollback_of`` links a rollback rollout to the one it superseded.
"""
import time

from sqlalchemy import Column, String, Float, JSON

from devicekit.db import Base

# status
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_ROLLED_BACK = "rolled_back"
STATUS_PAUSED = "paused"


class AgentRollout(Base):
    __tablename__ = "agent_rollouts"

    id = Column(String, primary_key=True)
    release_id = Column(String, nullable=False, index=True)
    target_kind = Column(String, nullable=False, default="all")   # all | group | fql
    target_value = Column(String, nullable=True)
    stage = Column(String, nullable=False, default="canary")      # canary | staged | full
    status = Column(String, nullable=False, default=STATUS_ACTIVE, index=True)
    config = Column(JSON, default=dict)
    stage_entered_at = Column(Float, nullable=True)
    rollback_of = Column(String, nullable=True)
    status_detail = Column(JSON, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)
    created_by = Column(String, nullable=True)
    workspace_id = Column(String, nullable=True, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "release_id": self.release_id,
            "target_kind": self.target_kind,
            "target_value": self.target_value,
            "stage": self.stage,
            "status": self.status,
            "config": self.config or {},
            "stage_entered_at": self.stage_entered_at,
            "rollback_of": self.rollback_of,
            "status_detail": self.status_detail,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "workspace_id": self.workspace_id,
        }
