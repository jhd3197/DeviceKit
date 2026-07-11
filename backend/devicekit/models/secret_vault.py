"""Encrypted secrets vault (plan 20, part 5).

``Vault`` groups ``Secret`` rows (WiFi passwords, app logins, third-party API keys). Values are
Fernet-encrypted at rest **reusing** ``notifications/crypto.py`` (same ``DEVICEKIT_SECRET_KEY``),
stored as ``enc:``-prefixed tokens and only decrypted in-process on an explicit reveal / at
automation-run injection time. Vaults are ``workspace_id``-scoped (nullable ⇒ global).

Gotcha carried from the crypto module: a solo-localhost deploy must keep ``DEVICEKIT_SECRET_KEY``
stable across reinstalls or every stored secret becomes undecryptable — the crypto module already
warns loudly when the key is the dev fallback.
"""
import time
import uuid

from sqlalchemy import Column, String, Float, Text, UniqueConstraint

from devicekit.db import Base


class Vault(Base):
    __tablename__ = "vaults"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, default="")
    workspace_id = Column(String, nullable=True, index=True)   # NULL = global
    created_by = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)

    def to_dict(self, secret_count=None):
        d = {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description or "",
            "workspace_id": self.workspace_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if secret_count is not None:
            d["secret_count"] = secret_count
        return d


class Secret(Base):
    __tablename__ = "vault_secrets"
    __table_args__ = (UniqueConstraint("vault_id", "key", name="uq_vault_secret_key"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vault_id = Column(String, nullable=False, index=True)
    key = Column(String, nullable=False)                       # env-var name, e.g. WIFI_PASSWORD
    value = Column(Text, nullable=False)                       # enc:-prefixed ciphertext
    description = Column(Text, default="")
    expires_at = Column(Float, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)

    def is_expired(self, now=None):
        return self.expires_at is not None and (now or time.time()) >= self.expires_at

    def to_dict(self, masked=True, value=None):
        """Masked by default — the raw value is only included on the explicit reveal path."""
        d = {
            "id": self.id,
            "vault_id": self.vault_id,
            "key": self.key,
            "description": self.description or "",
            "expires_at": self.expires_at,
            "expired": self.is_expired(),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "has_value": bool(self.value),
        }
        d["value"] = "••••••••" if masked else value
        return d
