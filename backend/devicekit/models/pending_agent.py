"""Pending-agent enrollment row (plan 07, RustDesk-style pairing).

The on-device agent starts an enroll→poll→claim handshake: it POSTs its device info and
gets back a short rotating pairing ``code``; a ``PendingAgent`` row holds that code until an
operator claims it from the dashboard (confirming with the panel passphrase). On claim the
row mints a per-device HMAC secret, promotes the device into ``agent_devices``, and is
deleted. Unclaimed rows expire (``expires_at``) so codes don't linger.
"""
import uuid

from sqlalchemy import Column, String, Float, JSON, Boolean

from devicekit.db import Base


class PendingAgent(Base):
    __tablename__ = "pending_agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, index=True, nullable=False)     # 6-char pairing code shown on device
    device_id = Column(String, nullable=False)            # provisional id derived from info
    info = Column(JSON, default=dict)                      # device info reported at enroll
    serial = Column(String, nullable=True)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    claimed = Column(Boolean, default=False)              # set when an operator claims the code
    # After claim the minted secret is stashed here so the agent's next poll receives it
    # exactly once (then the row is deleted).
    issued_secret = Column(String, nullable=True)
    last_ip = Column(String, nullable=True)

    def to_dict(self, include_secret=False):
        d = {
            "id": self.id,
            "code": self.code,
            "device_id": self.device_id,
            "info": self.info or {},
            "serial": self.serial,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "claimed": bool(self.claimed),
        }
        if include_secret:
            d["issued_secret"] = self.issued_secret
        return d
