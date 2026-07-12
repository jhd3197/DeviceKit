"""Scrub-first redaction helpers (plan 25 part 6).

ServerKit's ``support_bundle_service`` lesson: a diagnostic bundle is worthless if it leaks
the secrets it was meant to help debug. Two primitives, used by both the debug bundles and the
backup config snapshot:

* ``scrub`` — redact free text: JWTs, ``Authorization: Bearer/Basic`` headers, and
  ``key=secret`` / ``key: secret`` assignments for sensitive-looking keys.
* ``types_only`` — reduce a settings/config dict to **keys + value types**, never the values,
  so "which knobs exist" is visible while "what they're set to" never is.
"""
import re

_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*:\s*)(bearer|basic)\s+\S+")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}")
# key = value / key: value where the key looks sensitive.
_SECRET_KV = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|auth)\b(\s*[=:]\s*)(\"?)([^\s\"',}]+)")

_REDACTED = "[REDACTED]"


def scrub(text):
    """Redact secrets from free text. Non-str input is returned unchanged."""
    if not isinstance(text, str) or not text:
        return text
    text = _JWT.sub(_REDACTED, text)
    text = _AUTH_HEADER.sub(lambda m: m.group(1) + m.group(2) + " " + _REDACTED, text)
    text = _BEARER.sub(lambda m: m.group(1) + " " + _REDACTED, text)
    text = _SECRET_KV.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + _REDACTED, text)
    return text


def types_only(mapping):
    """Reduce a dict to ``{key: type_name}`` — keys + value types, never the values."""
    if not isinstance(mapping, dict):
        return {}
    return {str(k): type(v).__name__ for k, v in mapping.items()}
