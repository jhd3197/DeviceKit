"""Hashed, scoped API keys (plan 20, part 2).

Retires the single global ``API_KEY`` as the *forward* path (the legacy key still validates for
back-compat, deprecated). A ``dk_``-prefixed key is shown to its creator exactly once; the row
stores only the sha256 hash plus a display prefix, a JSON scope list (with wildcard matching —
``devices:*`` ⇒ ``devices:read``), an optional expiry, and revoke/last-used bookkeeping. This is
the axis plan 21's public API + MCP server authenticate against; the ``X-Agent-Token`` machine
identity stays orthogonal.
"""
import time
import uuid

from sqlalchemy import Column, String, Float, JSON

from devicekit.db import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False, index=True)   # display only, e.g. "dk_ab12cd34"
    key_hash = Column(String, nullable=False, unique=True, index=True)
    scopes = Column(JSON, default=list)                   # ["devices:*", "automations:read", ...]
    created_by = Column(String, nullable=True)            # user_id of the creator (attribution)
    created_at = Column(Float, nullable=False, default=time.time)
    expires_at = Column(Float, nullable=True)
    revoked_at = Column(Float, nullable=True)
    last_used_at = Column(Float, nullable=True)
    last_used_ip = Column(String, nullable=True)

    def is_active(self, now=None):
        now = now or time.time()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return True

    def status(self, now=None):
        now = now or time.time()
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and now >= self.expires_at:
            return "expired"
        return "active"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.prefix,
            "scopes": self.scopes or [],
            "created_by": self.created_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "last_used_at": self.last_used_at,
            "last_used_ip": self.last_used_ip,
            "status": self.status(),
        }
