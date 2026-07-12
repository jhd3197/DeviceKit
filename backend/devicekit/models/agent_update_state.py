"""Per-(rollout, device) OTA update state (plan 25 part 3).

Tracks what each device did with an offered release — the raw material for both the
rollout's advance/rollback decision (aggregate installed/failed counts) and **crash-loop
backoff**: once a device has failed ``attempts`` times it is no longer offered the update,
so a device that boot-loops on a bad build stops re-downloading it.
"""
import time

from sqlalchemy import Column, String, Integer, Float, UniqueConstraint

from devicekit.db import Base

# status lifecycle a device moves through for one offered release.
STATUS_OFFERED = "offered"
STATUS_DOWNLOADING = "downloading"
STATUS_INSTALLING = "installing"
STATUS_INSTALLED = "installed"
STATUS_FAILED = "failed"

TERMINAL = {STATUS_INSTALLED, STATUS_FAILED}


class AgentUpdateState(Base):
    __tablename__ = "agent_update_states"
    __table_args__ = (
        UniqueConstraint("rollout_id", "device_id", name="uq_update_rollout_device"),
    )

    id = Column(String, primary_key=True)
    rollout_id = Column(String, nullable=False, index=True)
    device_id = Column(String, nullable=False, index=True)
    release_id = Column(String, nullable=False)
    target_version_code = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default=STATUS_OFFERED)
    attempts = Column(Integer, nullable=False, default=0)   # failed install attempts
    last_error = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "rollout_id": self.rollout_id,
            "device_id": self.device_id,
            "release_id": self.release_id,
            "target_version_code": self.target_version_code,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
