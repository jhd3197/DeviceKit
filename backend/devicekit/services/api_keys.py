"""API-key primitives (plan 20, part 2): generation, hashing, and scope validation.

Kept separate from the mixin so the crypto/format decisions live in one place. A key is
``dk_`` + 43 url-safe chars; only its sha256 hash is ever persisted.
"""
import hashlib
import secrets

from devicekit.services.permissions import FEATURES

KEY_PREFIX = "dk_"          # avoids ``sk_``, which reads as an OpenAI key
_PREFIX_DISPLAY_LEN = 11    # "dk_" + 8 chars, stored for display

# Valid scope tokens: "*", "<feature>:*", "<feature>:read", "<feature>:write".
_ACTIONS = ("read", "write")


def generate_key():
    """Return ``(raw_key, prefix, key_hash)``. The raw key is shown to the user exactly once."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:_PREFIX_DISPLAY_LEN], hash_key(raw)


def hash_key(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def looks_like_key(raw):
    return isinstance(raw, str) and raw.startswith(KEY_PREFIX)


def available_scopes():
    """The full catalog of assignable scopes, for the key-creation UI."""
    scopes = ["*"]
    for f in FEATURES:
        scopes.append(f"{f}:*")
        scopes.extend(f"{f}:{a}" for a in _ACTIONS)
    return scopes


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
