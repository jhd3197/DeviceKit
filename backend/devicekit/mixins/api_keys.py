"""Scoped API-key lifecycle + authentication (plan 20, part 2).

Owns create / list / revoke / rotate and the ``resolve_api_key_principal`` hook that
``IdentityMixin.resolve_principal`` calls (via ``getattr``) before falling back to the legacy
global key. A presented ``dk_`` key resolves to an ``apikey`` principal whose *scopes* — not a
role matrix — gate the request.
"""
import time
import logging

from devicekit.db import session_scope
from devicekit.models.api_key import ApiKey
from devicekit.services.api_keys import (
    generate_key, hash_key, looks_like_key, validate_scopes, available_scopes,
)
from devicekit.services.principal import Principal

logger = logging.getLogger(__name__)

# Don't rewrite last_used on every single request — only when it's this stale (seconds).
_LAST_USED_THROTTLE = 60.0


class ApiKeysMixin:
    """Hashed, scoped API keys."""

    def create_api_key(self, name, scopes=None, created_by=None,
                       expires_at=None, expires_in_days=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        scopes = validate_scopes(scopes)
        if not scopes:
            raise ValueError("at least one scope is required")
        if expires_at is None and expires_in_days:
            expires_at = time.time() + float(expires_in_days) * 86400
        raw, prefix, key_hash = generate_key()
        with session_scope() as s:
            row = ApiKey(
                name=name, prefix=prefix, key_hash=key_hash, scopes=scopes,
                created_by=created_by, created_at=time.time(), expires_at=expires_at,
            )
            s.add(row)
            s.flush()
            result = row.to_dict()
        # The raw key is returned exactly once and never stored.
        result["key"] = raw
        return result

    def list_api_keys(self, include_revoked=True):
        with session_scope() as s:
            q = s.query(ApiKey).order_by(ApiKey.created_at.desc())
            rows = q.all()
        keys = [r.to_dict() for r in rows]
        if not include_revoked:
            keys = [k for k in keys if k["status"] != "revoked"]
        return keys

    def get_api_key(self, key_id):
        with session_scope() as s:
            row = s.get(ApiKey, key_id)
            return row.to_dict() if row else None

    def revoke_api_key(self, key_id):
        with session_scope() as s:
            row = s.get(ApiKey, key_id)
            if not row:
                raise ValueError("api key not found")
            if row.revoked_at is None:
                row.revoked_at = time.time()
            return row.to_dict()

    def rotate_api_key(self, key_id):
        """Revoke the old key and mint a new one with the same name/scopes/expiry config.
        Returns the new key dict (including the one-time raw ``key``)."""
        with session_scope() as s:
            row = s.get(ApiKey, key_id)
            if not row:
                raise ValueError("api key not found")
            name, scopes, created_by, expires_at = (
                row.name, list(row.scopes or []), row.created_by, row.expires_at)
            if row.revoked_at is None:
                row.revoked_at = time.time()
        return self.create_api_key(name, scopes=scopes, created_by=created_by,
                                   expires_at=expires_at)

    def resolve_api_key_principal(self, raw, request=None):
        """Resolve a presented ``dk_`` key to an ``apikey`` principal, or ``None``.

        Returns ``None`` for a non-``dk_`` value so the caller falls through to the legacy key.
        Updates last-used bookkeeping (throttled) as a side effect."""
        if not looks_like_key(raw):
            return None
        now = time.time()
        with session_scope() as s:
            row = s.query(ApiKey).filter(ApiKey.key_hash == hash_key(raw)).first()
            if not row or not row.is_active(now):
                return None
            scopes = list(row.scopes or [])
            key_id = row.id
            if row.last_used_at is None or (now - row.last_used_at) > _LAST_USED_THROTTLE:
                row.last_used_at = now
                if request is not None:
                    row.last_used_ip = getattr(request, "remote_addr", None)
        return Principal(kind="apikey", scopes=scopes, api_key_id=key_id)

    @staticmethod
    def api_key_scopes_catalog():
        return available_scopes()
