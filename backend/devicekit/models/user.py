"""User + login-session models (plan 20, part 1).

DeviceKit had no users — one global ``API_KEY`` and everyone who held it was root. ``User`` adds
real identities with a global role and an optional per-feature permission override; ``UserSession``
is the server side of a login (an opaque token, stored only as its sha256 hash, with an expiry).

String-UUID PKs + float-epoch timestamps to match the rest of the schema (ServerKit uses int PKs
and ``DateTime`` — we ported the pattern, not the columns).
"""
import time
import uuid

from sqlalchemy import Column, String, Float, Boolean, JSON

from devicekit.db import Base
from devicekit.services.permissions import resolve_permissions


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")   # admin | operator | viewer
    permissions = Column(JSON, nullable=True)                 # per-feature narrow-only override
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)
    last_login_at = Column(Float, nullable=True)

    def effective_permissions(self):
        """The resolved {feature: {read, write}} matrix (role template + override)."""
        return resolve_permissions(self.role, self.permissions)

    def to_dict(self, include_permissions=True):
        d = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": bool(self.is_active),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
        }
        if include_permissions:
            d["permissions"] = self.permissions or {}
            d["effective_permissions"] = self.effective_permissions()
        return d


class UserSession(Base):
    """A login session. The raw token is returned to the client once and never stored — only
    its sha256 hash lives here, so a database leak can't be replayed as live sessions."""

    __tablename__ = "user_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(Float, nullable=False, default=time.time)
    expires_at = Column(Float, nullable=False, index=True)
    last_seen_at = Column(Float, nullable=True)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    def is_expired(self, now=None):
        return (now or time.time()) >= self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_seen_at": self.last_seen_at,
            "ip": self.ip,
            "user_agent": self.user_agent,
        }
