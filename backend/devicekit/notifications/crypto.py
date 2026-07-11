"""Symmetric encryption for notification channel secrets at rest (plan 06.2).

Channel configs hold secrets — a Slack webhook URL embeds a token, SMTP needs a password.
Those are Fernet-encrypted before they touch the database and decrypted only in-process when
a delivery is sent. Non-secret config (severity threshold, format) is stored in the clear.

Key source: ``DEVICEKIT_SECRET_KEY`` (a Fernet key or any passphrase — a passphrase is hashed
to a 32-byte key). With no key set, a **deterministic dev fallback** is used so values still
round-trip across restarts; it is NOT secure and logs a one-time warning. Set the env var in
any real deployment.
"""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_PREFIX = "enc:"
_warned = False


def _fernet():
    global _warned
    raw = os.environ.get("DEVICEKIT_SECRET_KEY")
    if raw:
        if len(raw) == 44:  # looks like a ready-made Fernet key
            try:
                return Fernet(raw.encode())
            except Exception:
                pass
        key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(key)
    if not _warned:
        logger.warning(
            "DEVICEKIT_SECRET_KEY not set — notification secrets use an insecure dev key. "
            "Set DEVICEKIT_SECRET_KEY in production.")
        _warned = True
    key = base64.urlsafe_b64encode(hashlib.sha256(b"devicekit-dev-secret").digest())
    return Fernet(key)


def encrypt(value):
    """Encrypt a string, returning an ``enc:``-prefixed token. ``None``/empty pass through."""
    if not value:
        return value
    token = _fernet().encrypt(str(value).encode()).decode()
    return _PREFIX + token


def decrypt(value):
    """Decrypt an ``enc:``-prefixed token. A plaintext (un-prefixed) or undecryptable value is
    returned unchanged, so pre-encryption data and key rotation degrade gracefully."""
    if not value or not isinstance(value, str) or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except (InvalidToken, Exception):
        logger.warning("Could not decrypt a notification secret (key changed?)")
        return ""


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(_PREFIX)
