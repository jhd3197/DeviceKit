"""Identity, sessions & principal resolution (plan 20, part 1).

This is the mixin that turns DeviceKit's flat ``validate_api_key`` string-compare into
*resolve principal → attach to request → gate*. It owns:

* user CRUD (create/list/update/delete, password + role + narrow-only permission override),
* login sessions (opaque token, stored hashed, with expiry), and
* ``resolve_principal(request)`` — the single entry point the auth gate calls to figure out who
  is behind a request.

**Solo mode is unchanged:** with auth disabled (no ``API_KEY``) and no real users yet, every
request resolves to a full-access ``solo`` principal — byte-for-byte the historical behavior.
Creating the first user flips the instance into "login required" (mirrors ServerKit's
scope-on-activation rule: nothing changes until you opt in).
"""
import os
import time
import uuid
import hashlib
import secrets
import logging

from devicekit.db import session_scope
from devicekit.models.user import User, UserSession
from devicekit.services.passwords import hash_password, verify_password
from devicekit.services.permissions import (
    ROLES, ROLE_PERMISSION_TEMPLATES, validate_overrides, resolve_permissions,
)
from devicekit.services.principal import Principal

logger = logging.getLogger(__name__)

# Login session lifetime. Overridable so a deployment can shorten it; default 7 days.
SESSION_TTL_SECONDS = float(os.getenv("DEVICEKIT_SESSION_TTL", str(7 * 24 * 3600)))


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IdentityMixin:
    """Users, login sessions, and request-principal resolution."""

    _has_users_flag = None  # lazily-computed cache; invalidated on user create/delete

    # -----------------------------------------------------------------
    # Boot
    # -----------------------------------------------------------------
    def init_identity(self):
        """Reset the user-count cache and optionally bootstrap an admin from the environment.

        ``DEVICEKIT_ADMIN_USERNAME`` + ``DEVICEKIT_ADMIN_PASSWORD`` seed a first admin on a
        users-less instance so a fresh deploy isn't a chicken-and-egg lockout. Idempotent."""
        self._has_users_flag = None
        username = os.getenv("DEVICEKIT_ADMIN_USERNAME")
        password = os.getenv("DEVICEKIT_ADMIN_PASSWORD")
        if username and password and not self.has_users():
            try:
                self.create_user(username, password, role="admin",
                                 email=os.getenv("DEVICEKIT_ADMIN_EMAIL"))
                logger.info(f"Bootstrapped admin user '{username}' from environment")
            except Exception as e:
                logger.warning(f"Admin bootstrap skipped: {e}")

    # -----------------------------------------------------------------
    # User CRUD
    # -----------------------------------------------------------------
    def has_users(self):
        """Whether any user exists (cached). Drives solo-mode: no users ⇒ solo full access."""
        if self._has_users_flag is None:
            with session_scope() as s:
                self._has_users_flag = s.query(User.id).first() is not None
        return self._has_users_flag

    def create_user(self, username, password, role="viewer", email=None,
                    permissions=None, is_active=True):
        username = (username or "").strip()
        if not username:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        overrides = validate_overrides(permissions, role) if permissions else None
        with session_scope() as s:
            if s.query(User).filter(User.username == username).first():
                raise ValueError(f"username already exists: {username}")
            if email and s.query(User).filter(User.email == email).first():
                raise ValueError(f"email already exists: {email}")
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                email=(email or None),
                password_hash=hash_password(password),
                role=role,
                permissions=(overrides or None),
                is_active=bool(is_active),
                created_at=time.time(),
            )
            s.add(user)
            s.flush()
            result = user.to_dict()
        self._has_users_flag = True
        return result

    def get_user(self, user_id):
        with session_scope() as s:
            user = s.get(User, user_id)
            return user.to_dict() if user else None

    def list_users(self):
        with session_scope() as s:
            rows = s.query(User).order_by(User.created_at.asc()).all()
            return [u.to_dict() for u in rows]

    def update_user(self, user_id, role=None, email=None, permissions=None,
                    is_active=None, password=None):
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user:
                raise ValueError("user not found")
            if role is not None:
                if role not in ROLES:
                    raise ValueError(f"unknown role: {role}")
                # Guard against demoting the last admin out of existence.
                if user.role == "admin" and role != "admin" and self._admin_count(s) <= 1:
                    raise ValueError("cannot demote the last admin")
                user.role = role
            if email is not None:
                email = email.strip() or None
                if email and s.query(User).filter(User.email == email,
                                                   User.id != user_id).first():
                    raise ValueError(f"email already exists: {email}")
                user.email = email
            if permissions is not None:
                # Validate against the *effective* role (post-update) so a role+override
                # change in one call is checked coherently.
                user.permissions = validate_overrides(permissions, user.role) or None
            if is_active is not None:
                if not is_active and user.role == "admin" and self._admin_count(s) <= 1:
                    raise ValueError("cannot deactivate the last admin")
                user.is_active = bool(is_active)
            if password:
                user.password_hash = hash_password(password)
            user.updated_at = time.time()
            return user.to_dict()

    def delete_user(self, user_id):
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user:
                raise ValueError("user not found")
            if user.role == "admin" and self._admin_count(s) <= 1:
                raise ValueError("cannot delete the last admin")
            s.delete(user)
            # Revoke that user's live sessions along with the account.
            s.query(UserSession).filter(UserSession.user_id == user_id).delete()
        self._has_users_flag = None  # recompute on next check
        return True

    @staticmethod
    def _admin_count(session):
        return session.query(User).filter(User.role == "admin",
                                          User.is_active.is_(True)).count()

    def check_password(self, username, password):
        """Return the user dict when username+password match an active user, else ``None``.

        Side-effect-free — does *not* stamp ``last_login_at``, so a 2FA step (plan 20 part 6) can
        gate before the login is considered complete."""
        with session_scope() as s:
            user = s.query(User).filter(User.username == (username or "").strip()).first()
            if not user or not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return user.to_dict()

    def touch_last_login(self, user_id):
        with session_scope() as s:
            user = s.get(User, user_id)
            if user:
                user.last_login_at = time.time()

    def verify_credentials(self, username, password):
        """Return the user dict on a correct, active login (and stamp ``last_login_at``); else
        ``None``. The single-factor path used where 2FA isn't in play."""
        user = self.check_password(username, password)
        if user:
            self.touch_last_login(user["id"])
        return user

    # -----------------------------------------------------------------
    # Login sessions
    # -----------------------------------------------------------------
    def create_session(self, user_id, ip=None, user_agent=None, ttl=None):
        """Mint a session; returns the raw opaque token (shown to the client exactly once)."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with session_scope() as s:
            s.add(UserSession(
                id=str(uuid.uuid4()),
                token_hash=_hash_token(token),
                user_id=user_id,
                created_at=now,
                expires_at=now + (ttl or SESSION_TTL_SECONDS),
                last_seen_at=now,
                ip=ip,
                user_agent=(user_agent or "")[:400] or None,
            ))
        return token

    def delete_session(self, token):
        if not token:
            return False
        with session_scope() as s:
            deleted = s.query(UserSession).filter(
                UserSession.token_hash == _hash_token(token)).delete()
        return bool(deleted)

    def cleanup_expired_sessions(self):
        with session_scope() as s:
            return s.query(UserSession).filter(
                UserSession.expires_at < time.time()).delete()

    def _principal_from_session(self, token):
        if not token:
            return None
        now = time.time()
        with session_scope() as s:
            row = s.query(UserSession).filter(
                UserSession.token_hash == _hash_token(token)).first()
            if not row:
                return None
            if row.is_expired(now):
                s.delete(row)
                return None
            user = s.get(User, row.user_id)
            if not user or not user.is_active:
                s.delete(row)
                return None
            row.last_seen_at = now
            return self._principal_from_user(user)

    @staticmethod
    def _principal_from_user(user):
        return Principal(
            kind="user",
            user_id=user.id,
            username=user.username,
            role=user.role,
            permissions=user.effective_permissions(),
            full_access=(user.role == "admin"),
        )

    # -----------------------------------------------------------------
    # Principal builders for the non-user identities
    # -----------------------------------------------------------------
    @staticmethod
    def solo_principal():
        return Principal(kind="solo", username="solo", role="admin", full_access=True)

    @staticmethod
    def legacy_principal():
        return Principal(kind="legacy", username="api-key", role="admin", full_access=True)

    @staticmethod
    def agent_principal():
        return Principal(kind="agent", username="agent")

    @staticmethod
    def anonymous_principal():
        return Principal(kind="anonymous")

    # -----------------------------------------------------------------
    # The gate's single entry point
    # -----------------------------------------------------------------
    def resolve_principal(self, request):
        """Resolve the principal behind a request, or ``None`` if authentication is required.

        Order: session token → API key (scoped dk_ key if plan-20-part-2 is live, else the
        legacy global key) → solo fallback. Returns ``None`` only when credentials are required
        but absent/invalid; the gate turns that into a 401."""
        # 1. Login session (header, bearer, or SSE query param).
        token = self._session_token_from(request)
        if token:
            principal = self._principal_from_session(token)
            if principal is not None:
                return principal

        # 2. API key — header or query param (EventSource/MJPEG can't set headers).
        key = request.headers.get("X-API-Key") or request.args.get("api_key", "")
        if key:
            # Scoped dk_ keys (plan 20 part 2) take precedence when that mixin is present.
            resolver = getattr(self, "resolve_api_key_principal", None)
            if resolver is not None:
                principal = resolver(key, request)
                if principal is not None:
                    return principal
            if self._api_key and key == self._api_key:
                return self.legacy_principal()
            return None  # a key was presented but matched nothing → reject

        # 3. No credentials. Solo mode (auth disabled + no users) keeps full access;
        # otherwise authentication is required.
        if not self._api_key and not self.has_users():
            return self.solo_principal()
        return None

    @staticmethod
    def _session_token_from(request):
        token = request.headers.get("X-Session-Token")
        if token:
            return token.strip()
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return request.args.get("session_token") or request.cookies.get("dk_session")

    # -----------------------------------------------------------------
    # Schema surface for the permission-matrix editor UI
    # -----------------------------------------------------------------
    @staticmethod
    def permission_schema():
        from devicekit.services.permissions import FEATURES
        return {
            "features": list(FEATURES),
            "roles": list(ROLES),
            "templates": ROLE_PERMISSION_TEMPLATES,
        }
