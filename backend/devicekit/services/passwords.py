"""Password hashing — bcrypt, isolated here so the algorithm choice lives in one place.

bcrypt truncates silently at 72 bytes; we truncate explicitly so an over-long password can
never hash to the same value as its 72-byte prefix in a surprising way. Verification never
raises — a malformed stored hash resolves to ``False`` rather than a 500.
"""
import bcrypt

_MAX = 72  # bcrypt's hard input limit, in bytes


def hash_password(password):
    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode("utf-8")[:_MAX], bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_MAX], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
