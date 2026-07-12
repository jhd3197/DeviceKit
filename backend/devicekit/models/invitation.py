"""User invitations (plan 20, part 6).

A token + a role/permission preset. The copy-link flow works without SMTP: the raw token is shown
to the admin once and pasted into an invite URL; only its sha256 hash is stored. Accepting an
invitation creates the ``User`` with the preset role/permissions (and, when set, a workspace
membership).
"""
import time
import uuid

from sqlalchemy import Column, String, Float, JSON

from devicekit.db import Base


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String, nullable=False, unique=True, index=True)
    email = Column(String, nullable=True)                 # optional hint, not verified
    role = Column(String, nullable=False, default="viewer")
    permissions = Column(JSON, nullable=True)             # per-feature override preset
    workspace_id = Column(String, nullable=True)          # optional workspace membership on accept
    workspace_role = Column(String, nullable=True)        # role within that workspace
    invited_by = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    expires_at = Column(Float, nullable=True)
    accepted_at = Column(Float, nullable=True)
    accepted_user_id = Column(String, nullable=True)

    def status(self, now=None):
        now = now or time.time()
        if self.accepted_at is not None:
            return "accepted"
        if self.expires_at is not None and now >= self.expires_at:
            return "expired"
        return "pending"

    def is_redeemable(self, now=None):
        return self.status(now) == "pending"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "permissions": self.permissions or {},
            "workspace_id": self.workspace_id,
            "workspace_role": self.workspace_role,
            "invited_by": self.invited_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "accepted_at": self.accepted_at,
            "accepted_user_id": self.accepted_user_id,
            "status": self.status(),
        }
