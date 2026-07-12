"""TOTP 2FA + backup-code primitives (plan 20, part 6), thin wrappers over ``pyotp``.

Secrets are generated here and stored Fernet-encrypted (reusing ``notifications/crypto.py``).
Backup codes are single-use: shown once at enrollment, stored only as sha256 hashes, and consumed
on redemption.
"""
import hashlib
import secrets as _secrets

import pyotp

_ISSUER = "DeviceKit"
_BACKUP_CODE_COUNT = 10


def generate_secret():
    return pyotp.random_base32()


def provisioning_uri(secret, account_name):
    """The ``otpauth://`` URI an authenticator app scans (also renderable as a QR)."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name or "user", issuer_name=_ISSUER)


def verify_code(secret, code):
    if not secret or not code:
        return False
    try:
        # valid_window=1 tolerates a ±30s clock skew between server and phone.
        return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)
    except Exception:
        return False


def generate_backup_codes(n=_BACKUP_CODE_COUNT):
    """Return ``(plaintext_codes, hashes)``. Plaintext is shown once; only hashes are stored."""
    codes = ["-".join((_secrets.token_hex(2), _secrets.token_hex(2))) for _ in range(n)]
    return codes, [hash_backup_code(c) for c in codes]


def hash_backup_code(code):
    return hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()
