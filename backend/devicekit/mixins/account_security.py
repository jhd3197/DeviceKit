"""Account security & onboarding (plan 20, part 6) — the opt-in polish layer.

Adds, each independently activatable on top of part 1:

* **invitations** — token + role/permission preset; the copy-link flow works without SMTP.
* **TOTP 2FA + backup codes** — enroll / confirm / verify / disable, stored Fernet-encrypted.
* **progressive lockout** — 5 failed logins → 5/15/60-minute escalating backoff (in-memory,
  single-process).
* **require-2FA-with-grace** — a settings toggle whose grace window is anchored on
  ``max(user.created_at, policy_enabled_at)`` so flipping it on never insta-locks veterans.

``authenticate`` is the composed login: lockout → password → 2FA → session, returning a typed
result the ``/auth/login`` route renders.
"""
import time
import uuid
import hashlib
import secrets
import logging

from devicekit.db import session_scope
from devicekit.models.user import User
from devicekit.models.invitation import Invitation
from devicekit.notifications.crypto import encrypt, decrypt
from devicekit.services import totp as totp_svc
from devicekit.services.permissions import ROLES, validate_overrides

logger = logging.getLogger(__name__)

LOCKOUT_THRESHOLD = 5                     # failures before a lock kicks in
LOCKOUT_BACKOFFS_MIN = (5, 15, 60)        # escalating lock durations, in minutes


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AccountSecurityMixin:
    """Invitations, TOTP 2FA, progressive lockout, and the require-2FA policy."""

    _login_attempts = None   # {username: {count, locked_until, tier}} — in-memory, single-process

    # -----------------------------------------------------------------
    # Progressive lockout
    # -----------------------------------------------------------------
    def _attempts(self):
        if self._login_attempts is None:
            self._login_attempts = {}
        return self._login_attempts

    def _is_locked(self, username):
        rec = self._attempts().get(username)
        if not rec:
            return False, 0
        remaining = rec.get("locked_until", 0) - time.time()
        return (remaining > 0, int(remaining)) if remaining > 0 else (False, 0)

    def _record_failure(self, username):
        now = time.time()
        rec = self._attempts().setdefault(username, {"count": 0, "locked_until": 0, "tier": 0})
        rec["count"] += 1
        if rec["count"] % LOCKOUT_THRESHOLD == 0:
            backoff = LOCKOUT_BACKOFFS_MIN[min(rec["tier"], len(LOCKOUT_BACKOFFS_MIN) - 1)]
            rec["locked_until"] = now + backoff * 60
            rec["tier"] += 1

    def _clear_failures(self, username):
        self._attempts().pop(username, None)

    # -----------------------------------------------------------------
    # Composed login
    # -----------------------------------------------------------------
    def authenticate(self, username, password, code=None, ip=None, user_agent=None):
        """Full login: lockout → password → 2FA → session. Returns a typed result dict.

        Shapes: ``{ok, token, user, must_enroll_2fa}`` on success; ``{error, locked, retry_after}``
        when locked; ``{mfa_required: True}`` when a valid password needs a 2FA code; ``{error}``
        on bad credentials/code."""
        username = (username or "").strip()
        locked, retry_after = self._is_locked(username)
        if locked:
            return {"error": "Account temporarily locked", "locked": True,
                    "retry_after": retry_after}

        user = self.check_password(username, password)
        if not user:
            self._record_failure(username)
            return {"error": "Invalid credentials"}

        if user.get("totp_enabled"):
            if not code:
                return {"mfa_required": True}
            if not self.verify_totp(user["id"], code):
                self._record_failure(username)
                return {"error": "Invalid 2FA code", "mfa_required": True}

        self._clear_failures(username)
        self.touch_last_login(user["id"])
        token = self.create_session(user["id"], ip=ip, user_agent=user_agent)
        return {"ok": True, "token": token, "user": self.get_user(user["id"]),
                "must_enroll_2fa": self.twofa_policy_status(user).get("must_enroll", False)}

    # -----------------------------------------------------------------
    # TOTP 2FA
    # -----------------------------------------------------------------
    def start_totp_enrollment(self, user_id):
        """Stage a secret (not yet enabled) and return the provisioning URI + secret to scan."""
        secret = totp_svc.generate_secret()
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user:
                raise ValueError("user not found")
            user.totp_secret = encrypt(secret)   # staged; totp_enabled stays False until confirmed
            uri = totp_svc.provisioning_uri(secret, user.username)
        return {"secret": secret, "provisioning_uri": uri}

    def confirm_totp(self, user_id, code):
        """Verify the first code against the staged secret, enable 2FA, and return backup codes
        (shown exactly once)."""
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user or not user.totp_secret:
                raise ValueError("no pending 2FA enrollment")
            secret = decrypt(user.totp_secret)
            if not totp_svc.verify_code(secret, code):
                raise ValueError("invalid 2FA code")
            plaintext, hashes = totp_svc.generate_backup_codes()
            user.totp_enabled = True
            user.backup_codes = hashes
            user.updated_at = time.time()
        return {"backup_codes": plaintext}

    def disable_totp(self, user_id):
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user:
                raise ValueError("user not found")
            user.totp_secret = None
            user.totp_enabled = False
            user.backup_codes = None
            user.updated_at = time.time()
        return True

    def verify_totp(self, user_id, code):
        """Verify a TOTP code, or consume a single-use backup code."""
        with session_scope() as s:
            user = s.get(User, user_id)
            if not user or not user.totp_enabled:
                return False
            if user.totp_secret and totp_svc.verify_code(decrypt(user.totp_secret), code):
                return True
            codes = list(user.backup_codes or [])
            h = totp_svc.hash_backup_code(code)
            if h in codes:
                codes.remove(h)                 # single-use
                user.backup_codes = codes
                return True
        return False

    # -----------------------------------------------------------------
    # require-2FA policy (settings-backed, no new table)
    # -----------------------------------------------------------------
    def twofa_policy_status(self, user):
        """Whether this user must enroll in 2FA under the current policy, with the grace window
        anchored on ``max(created_at, policy_enabled_at)`` so enabling the policy never
        insta-locks an existing user."""
        required = bool(self.get_setting("security.require_2fa"))
        enrolled = bool(user.get("totp_enabled"))
        if not required or enrolled:
            return {"required": required, "enrolled": enrolled,
                    "in_grace": False, "grace_ends_at": None, "must_enroll": False}
        enabled_at = self.get_setting("security.require_2fa_enabled_at") or 0
        gd = self.get_setting("security.twofa_grace_days")   # 0 is valid (immediate), don't `or`
        grace_days = int(gd) if gd is not None else 7
        anchor = max(float(user.get("created_at") or 0), float(enabled_at))
        grace_ends_at = anchor + grace_days * 86400
        now = time.time()
        # grace_ends_at is the deadline: at or past it, enrollment is required (so a 0-day grace
        # forces it immediately). Before it, the user is still inside the window.
        return {"required": True, "enrolled": False,
                "in_grace": now < grace_ends_at, "grace_ends_at": grace_ends_at,
                "must_enroll": now >= grace_ends_at}

    def set_require_2fa(self, enabled):
        """Toggle the policy, stamping the enable time so the grace window can anchor on it."""
        self.set_setting("security.require_2fa", bool(enabled))
        if enabled and not self.get_setting("security.require_2fa_enabled_at"):
            self.set_setting("security.require_2fa_enabled_at", time.time())
        if not enabled:
            self.set_setting("security.require_2fa_enabled_at", None)
        return bool(enabled)

    # -----------------------------------------------------------------
    # Invitations
    # -----------------------------------------------------------------
    def create_invitation(self, role="viewer", email=None, permissions=None, workspace_id=None,
                          workspace_role=None, invited_by=None, expires_in_days=7):
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        overrides = validate_overrides(permissions, role) if permissions else None
        token = secrets.token_urlsafe(32)
        now = time.time()
        with session_scope() as s:
            inv = Invitation(
                id=str(uuid.uuid4()), token_hash=_hash_token(token), email=email, role=role,
                permissions=(overrides or None), workspace_id=workspace_id,
                workspace_role=workspace_role, invited_by=invited_by, created_at=now,
                expires_at=now + float(expires_in_days) * 86400)
            s.add(inv)
            s.flush()
            result = inv.to_dict()
        result["token"] = token   # returned once for the copy-link
        return result

    def list_invitations(self):
        with session_scope() as s:
            rows = s.query(Invitation).order_by(Invitation.created_at.desc()).all()
            return [i.to_dict() for i in rows]

    def get_invitation_preview(self, token):
        """Public preview for the accept page — role/email only, and only while redeemable."""
        with session_scope() as s:
            inv = s.query(Invitation).filter(Invitation.token_hash == _hash_token(token)).first()
            if not inv or not inv.is_redeemable():
                return None
            return {"role": inv.role, "email": inv.email, "workspace_id": inv.workspace_id,
                    "status": inv.status()}

    def accept_invitation(self, token, username, password):
        with session_scope() as s:
            inv = s.query(Invitation).filter(Invitation.token_hash == _hash_token(token)).first()
            if not inv or not inv.is_redeemable():
                raise ValueError("invitation is not valid")
            role, permissions = inv.role, inv.permissions
            workspace_id, workspace_role, inv_id = inv.workspace_id, inv.workspace_role, inv.id
        # Create the user via the identity mixin (its own session/validation).
        user = self.create_user(username, password, role=role, permissions=permissions)
        if workspace_id and hasattr(self, "add_member"):
            try:
                self.add_member(workspace_id, user["id"], role=workspace_role or "member")
            except Exception as e:
                logger.warning(f"Invitation workspace membership skipped: {e}")
        with session_scope() as s:
            inv = s.get(Invitation, inv_id)
            inv.accepted_at = time.time()
            inv.accepted_user_id = user["id"]
        return user

    def revoke_invitation(self, invitation_id):
        with session_scope() as s:
            inv = s.get(Invitation, invitation_id)
            if not inv:
                raise ValueError("invitation not found")
            s.delete(inv)
        return True
