"""API-key primitives (plan 20, part 2): generation, hashing, and scope validation.

Kept separate from the mixin so the crypto/format decisions live in one place. A key is
``dk_`` + 43 url-safe chars; only its sha256 hash is ever persisted.
"""
import hashlib
import secrets

# The assignable-scope catalog moved to the shared scope layer (plan 21) — it now includes
# the device-oriented verbs (devices:command, automations:run, …) beyond read/write pairs.
from devicekit.services.scopes import available_scopes  # noqa: F401  (re-export, back-compat)

KEY_PREFIX = "dk_"          # avoids ``sk_``, which reads as an OpenAI key
_PREFIX_DISPLAY_LEN = 11    # "dk_" + 8 chars, stored for display


def generate_key():
    """Return ``(raw_key, prefix, key_hash)``. The raw key is shown to the user exactly once."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:_PREFIX_DISPLAY_LEN], hash_key(raw)


def hash_key(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def looks_like_key(raw):
    return isinstance(raw, str) and raw.startswith(KEY_PREFIX)


def validate_scopes(scopes):
    """Normalize + validate a scope list. Returns a de-duplicated list; raises ``ValueError``
    on an unknown scope token."""
    if scopes is None:
        return []
    if not isinstance(scopes, (list, tuple)):
        raise ValueError("scopes must be a list")
    valid = set(available_scopes())
    out = []
    for scope in scopes:
        scope = (scope or "").strip()
        if not scope:
            continue
        if scope not in valid:
            raise ValueError(f"unknown scope: {scope}")
        if scope not in out:
            out.append(scope)
    return out
