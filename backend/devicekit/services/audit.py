"""Audit helpers (plan 20, part 3): sensitive-key redaction + proxy-aware client identity.

Pure functions so the redaction policy and the "what IP is the client really" logic live in one
place and can be unit-tested without a request. The audit trail must never persist a secret that
happened to ride in a request/response body, so redaction runs before anything is stored.
"""

# Substring match (case-insensitive) against dict keys. Anything containing one of these is
# masked. Deliberately broad — a false-positive redaction is harmless, a leaked secret is not.
_SENSITIVE = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "auth", "passphrase", "private", "credential", "session", "cookie", "key_hash",
)

_MASK = "***"
_MAX_DEPTH = 6


def _is_sensitive(key):
    k = str(key).lower()
    return any(marker in k for marker in _SENSITIVE)


def redact(value, _depth=0):
    """Return a deep copy of ``value`` with sensitive dict values masked.

    Recurses into dicts/lists; a key that looks secret has its entire value replaced (so nested
    secret structures are masked wholesale). Depth-bounded against pathological nesting."""
    if _depth >= _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k] = _MASK if _is_sensitive(k) else redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, _depth + 1) for v in value]
    return value


def client_ip(request):
    """Proxy-aware client IP: first hop of ``X-Forwarded-For``, then ``X-Real-IP``, then the
    socket peer. DeviceKit commonly runs behind nginx (see ``nginx.conf``)."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or getattr(request, "remote_addr", None)


def user_agent(request):
    ua = request.headers.get("User-Agent")
    return ua[:400] if ua else None
