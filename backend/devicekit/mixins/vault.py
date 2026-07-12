"""Encrypted secrets vault service (plan 20, part 5).

Vault + secret CRUD with values Fernet-encrypted via ``notifications/crypto.py``. Lists/API are
masked; a separate ``reveal_secret`` path decrypts one value on demand. ``resolve_env_dict`` is the
injection hook automation runs (plan 22) call at execution time to turn a vault into a
``{ENV_VAR: value}`` map.
"""
import time
import uuid
import logging

from slugify import slugify

from devicekit.db import session_scope
from devicekit.models.secret_vault import Vault, Secret
from devicekit.notifications.crypto import encrypt, decrypt
from devicekit.services.workspace import scope_query

logger = logging.getLogger(__name__)


class VaultMixin:
    """Fernet-encrypted secrets vault."""

    # -----------------------------------------------------------------
    # Vaults
    # -----------------------------------------------------------------
    def create_vault(self, name, slug=None, description="", workspace_id=None, created_by=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        slug = slugify(slug or name)
        if not slug:
            raise ValueError("could not derive a slug")
        with session_scope() as s:
            if s.query(Vault).filter(Vault.slug == slug).first():
                raise ValueError(f"vault slug already exists: {slug}")
            v = Vault(id=str(uuid.uuid4()), name=name, slug=slug, description=description or "",
                      workspace_id=workspace_id, created_by=created_by, created_at=time.time())
            s.add(v)
            s.flush()
            return v.to_dict(secret_count=0)

    def list_vaults(self, workspace_id=None):
        """List vaults, narrowed to a workspace when active (narrow-only, plan 20 part 4)."""
        with session_scope() as s:
            q = scope_query(s.query(Vault), Vault, workspace_id)
            vaults = q.order_by(Vault.created_at.asc()).all()
            out = []
            for v in vaults:
                count = s.query(Secret).filter(Secret.vault_id == v.id).count()
                out.append(v.to_dict(secret_count=count))
            return out

    def get_vault(self, vault_id):
        with session_scope() as s:
            v = s.get(Vault, vault_id)
            if not v:
                return None
            count = s.query(Secret).filter(Secret.vault_id == vault_id).count()
            return v.to_dict(secret_count=count)

    def delete_vault(self, vault_id):
        with session_scope() as s:
            v = s.get(Vault, vault_id)
            if not v:
                raise ValueError("vault not found")
            s.query(Secret).filter(Secret.vault_id == vault_id).delete()
            s.delete(v)
        return True

    # -----------------------------------------------------------------
    # Secrets
    # -----------------------------------------------------------------
    def set_secret(self, vault_id, key, value, description="", expires_at=None,
                   created_by=None):
        """Create or update (rotate) a secret. The value is encrypted before it touches the DB."""
        key = (key or "").strip()
        if not key:
            raise ValueError("key is required")
        if value is None or value == "":
            raise ValueError("value is required")
        now = time.time()
        with session_scope() as s:
            if not s.get(Vault, vault_id):
                raise ValueError("vault not found")
            row = s.query(Secret).filter(Secret.vault_id == vault_id,
                                         Secret.key == key).first()
            if row is None:
                row = Secret(id=str(uuid.uuid4()), vault_id=vault_id, key=key,
                             created_by=created_by, created_at=now)
                s.add(row)
            row.value = encrypt(str(value))
            if description:
                row.description = description
            row.expires_at = expires_at
            row.updated_at = now
            s.flush()
            return row.to_dict(masked=True)

    def list_secrets(self, vault_id):
        """Masked list — values are never included here (use ``reveal_secret``)."""
        with session_scope() as s:
            rows = s.query(Secret).filter(Secret.vault_id == vault_id).order_by(
                Secret.key.asc()).all()
            return [r.to_dict(masked=True) for r in rows]

    def reveal_secret(self, vault_id, key):
        """Decrypt and return one secret's value. The separate, auditable reveal path."""
        with session_scope() as s:
            row = s.query(Secret).filter(Secret.vault_id == vault_id,
                                         Secret.key == key).first()
            if not row:
                raise ValueError("secret not found")
            return row.to_dict(masked=False, value=decrypt(row.value))

    def delete_secret(self, vault_id, key):
        with session_scope() as s:
            deleted = s.query(Secret).filter(Secret.vault_id == vault_id,
                                             Secret.key == key).delete()
            if not deleted:
                raise ValueError("secret not found")
        return True

    def resolve_env_dict(self, vault_id, include_expired=False):
        """Decrypt every secret in a vault into a ``{KEY: value}`` map for injection into an
        automation run (plan 22). Expired secrets are skipped unless ``include_expired``."""
        now = time.time()
        env = {}
        with session_scope() as s:
            rows = s.query(Secret).filter(Secret.vault_id == vault_id).all()
            for row in rows:
                if not include_expired and row.is_expired(now):
                    continue
                env[row.key] = decrypt(row.value)
        return env
