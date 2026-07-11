"""Account security & onboarding (plan 20, part 6).

Covers TOTP enroll/confirm/verify + backup codes, the composed ``authenticate`` (2FA gate +
progressive lockout), invitations (create/preview/accept), and the require-2FA grace policy.
"""
import time

import pytest

from devicekit.mixins.account_security import AccountSecurityMixin, LOCKOUT_THRESHOLD
from devicekit.mixins.workspaces import WorkspacesMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.settings import SettingsMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.services import totp as totp_svc


class _SecClient(AccountSecurityMixin, WorkspacesMixin, SettingsMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None
        self._login_attempts = {}


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _SecClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- TOTP
def test_totp_enroll_confirm_verify(client):
    u = client.create_user("alice", "pw123456", role="admin")
    enroll = client.start_totp_enrollment(u["id"])
    assert enroll["provisioning_uri"].startswith("otpauth://")
    secret = enroll["secret"]
    # Not enabled until confirmed.
    assert client.get_user(u["id"])["totp_enabled"] is False
    # A wrong code is rejected.
    with pytest.raises(ValueError):
        client.confirm_totp(u["id"], "000000")
    # The right code enables 2FA and yields backup codes.
    code = totp_svc.pyotp.TOTP(secret).now()
    result = client.confirm_totp(u["id"], code)
    assert len(result["backup_codes"]) == 10
    assert client.get_user(u["id"])["totp_enabled"] is True
    # verify_totp accepts the live code…
    assert client.verify_totp(u["id"], totp_svc.pyotp.TOTP(secret).now())
    # …and consumes a single-use backup code.
    backup = result["backup_codes"][0]
    assert client.verify_totp(u["id"], backup) is True
    assert client.verify_totp(u["id"], backup) is False   # already used


def test_totp_secret_encrypted_at_rest(client):
    u = client.create_user("bob", "pw123456")
    enroll = client.start_totp_enrollment(u["id"])
    from devicekit.db import session_scope
    from devicekit.models.user import User
    from devicekit.notifications import crypto
    with session_scope() as s:
        row = s.get(User, u["id"])
        assert crypto.is_encrypted(row.totp_secret)
        assert enroll["secret"] not in row.totp_secret


# --------------------------------------------------------------- authenticate + lockout
def test_authenticate_password_only(client):
    client.create_user("carol", "pw123456", role="operator")
    r = client.authenticate("carol", "pw123456")
    assert r["ok"] and r["token"] and r["user"]["username"] == "carol"
    assert client.authenticate("carol", "wrong").get("error")


def test_authenticate_requires_2fa_when_enabled(client):
    u = client.create_user("dave", "pw123456")
    enroll = client.start_totp_enrollment(u["id"])
    client.confirm_totp(u["id"], totp_svc.pyotp.TOTP(enroll["secret"]).now())
    # Password alone → mfa_required, no session.
    r = client.authenticate("dave", "pw123456")
    assert r.get("mfa_required") and "token" not in r
    # Password + valid code → success.
    code = totp_svc.pyotp.TOTP(enroll["secret"]).now()
    r2 = client.authenticate("dave", "pw123456", code=code)
    assert r2["ok"]


def test_progressive_lockout(client):
    client.create_user("erin", "pw123456")
    for _ in range(LOCKOUT_THRESHOLD):
        client.authenticate("erin", "wrong")
    # Now locked, even with the correct password.
    r = client.authenticate("erin", "pw123456")
    assert r.get("locked") and r.get("retry_after", 0) > 0
    # Clearing the lock (simulate time passing) lets a good login through.
    client._login_attempts["erin"]["locked_until"] = time.time() - 1
    assert client.authenticate("erin", "pw123456")["ok"]


# --------------------------------------------------------------- invitations
def test_invitation_create_preview_accept(client):
    inv = client.create_invitation(role="operator", email="new@x.io", expires_in_days=3)
    assert inv["token"] and inv["status"] == "pending"
    preview = client.get_invitation_preview(inv["token"])
    assert preview["role"] == "operator" and preview["email"] == "new@x.io"
    # Accept creates the user with the preset role.
    user = client.accept_invitation(inv["token"], "newbie", "pw123456")
    assert user["role"] == "operator" and user["username"] == "newbie"
    # A used invite is no longer redeemable.
    assert client.get_invitation_preview(inv["token"]) is None
    with pytest.raises(ValueError):
        client.accept_invitation(inv["token"], "again", "pw123456")


def test_invitation_with_workspace_membership(client):
    ws = client.create_workspace("Team", created_by=None)
    inv = client.create_invitation(role="viewer", workspace_id=ws["id"],
                                   workspace_role="member")
    user = client.accept_invitation(inv["token"], "contractor", "pw123456")
    assert client.member_role(user["id"], ws["id"]) == "member"


def test_expired_invitation_not_redeemable(client):
    inv = client.create_invitation(role="viewer", expires_in_days=0)
    # expires_in_days=0 → expires_at == created_at → already expired.
    assert client.get_invitation_preview(inv["token"]) is None


# --------------------------------------------------------------- require-2FA grace policy
def test_require_2fa_grace_anchor(client):
    u = client.create_user("frank", "pw123456")
    # Policy off → nothing required.
    assert client.twofa_policy_status(client.get_user(u["id"]))["must_enroll"] is False
    # Turn the policy on now with a 0-day grace so an un-enrolled user is immediately required.
    client.set_require_2fa(True)
    client.set_setting("security.twofa_grace_days", 0)
    status = client.twofa_policy_status(client.get_user(u["id"]))
    assert status["required"] and not status["enrolled"] and status["must_enroll"]
    # With a long grace, the same user is inside the window (not yet forced).
    client.set_setting("security.twofa_grace_days", 30)
    assert client.twofa_policy_status(client.get_user(u["id"]))["in_grace"] is True
    # An enrolled user is never flagged.
    enroll = client.start_totp_enrollment(u["id"])
    client.confirm_totp(u["id"], totp_svc.pyotp.TOTP(enroll["secret"]).now())
    assert client.twofa_policy_status(client.get_user(u["id"]))["must_enroll"] is False
