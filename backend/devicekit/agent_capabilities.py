"""Capability + version negotiation (plan 25 part 2).

Two jobs, both pure (no device, no I/O), so they are shared and independently testable:

1. **Normalize the capability advertisement.** ``docs/FLEET_CONTRACT.md`` documents a wire
   discrepancy: the shipped Kotlin agent sends ``capabilities`` as a JSON *array of strings*
   (``["accessibility", ...]``) but the backend + FQL treat it as a *map*
   (``{screen_record: true, android_api: 34}``). ``normalize_capabilities`` accepts either
   shape and always returns a map, so an old array-sending agent still resolves ``can.*``
   and a new agent can advertise typed values.

2. **Negotiate the survey transport.** Richer batched probes (one round trip for a whole
   probe) are a *capability-gated optimization*. An agent that advertises ``batch_survey``
   can take the fast path; every other agent keeps the composed per-primitive path from
   phase 1 forever. Old agents work forever — that is the invariant this plan protects.
"""

# Capability an agent advertises when it can run a whole probe in one `survey.batch` command.
BATCH_SURVEY_CAPABILITY = "batch_survey"


def normalize_capabilities(raw):
    """Return a ``{key: value}`` capability map from either a legacy list or a map.

    * ``["a", "b"]`` → ``{"a": True, "b": True}`` (legacy array agent)
    * ``{"a": True, "android_api": 34}`` → passed through (values preserved)
    * ``None`` / anything else → ``{}``
    """
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (list, tuple)):
        return {str(k): True for k in raw if k is not None}
    return {}


def supports_batch_survey(capabilities):
    """True if the agent advertised the batched-survey optimization."""
    return bool((capabilities or {}).get(BATCH_SURVEY_CAPABILITY))


def extract_agent_version(info):
    """Pull ``(version_name, version_code)`` from a register payload's ``info``.

    The agent sends ``agent_version`` (a versionName string) and, once it advertises a
    numeric code, ``agent_version_code``. Both are optional; a legacy agent that only sends
    the string still gets a row in the fleet-version view. ``version_code`` is coerced to an
    int or left ``None`` (never a crash on a bad value).
    """
    info = info or {}
    name = info.get("agent_version") or info.get("version")
    code = info.get("agent_version_code") or info.get("version_code")
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    return (str(name) if name is not None else None), code
