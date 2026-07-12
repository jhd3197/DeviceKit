"""Device onboarding session (plan 25 part 4).

Formalizes enrollment as a state machine advanced on the job bus —
``pending → validating → provisioning → ready | failed`` — replacing today's ad-hoc pairing.
The ordered ``steps`` log is the audit trail of what happened at each transition; a
newly-``ready`` device has had its group policy applied (plan 23).
"""
import time

from sqlalchemy import Column, String, Float, JSON

from devicekit.db import Base

STATE_PENDING = "pending"
STATE_VALIDATING = "validating"
STATE_PROVISIONING = "provisioning"
STATE_READY = "ready"
STATE_FAILED = "failed"

TERMINAL_STATES = {STATE_READY, STATE_FAILED}
# Order the machine advances through (failed is an exit from any non-terminal state).
FORWARD_STATES = [STATE_PENDING, STATE_VALIDATING, STATE_PROVISIONING, STATE_READY]


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"

    id = Column(String, primary_key=True)
    device_id = Column(String, nullable=False, index=True)
    serial = Column(String, nullable=True)
    state = Column(String, nullable=False, default=STATE_PENDING, index=True)
    steps = Column(JSON, default=list)        # [{step, status, detail, at}]
    context = Column(JSON, default=dict)      # arbitrary caller context (trigger, source, …)
    error = Column(String, nullable=True)
    started_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)
    completed_at = Column(Float, nullable=True)
    workspace_id = Column(String, nullable=True, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "serial": self.serial,
            "state": self.state,
            "steps": self.steps or [],
            "context": self.context or {},
            "error": self.error,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "workspace_id": self.workspace_id,
        }
