"""Scaffold: render a ``devicekit.yaml`` FROM live device state (plan 23 part 6).

The reverse of apply — capture an existing device as a starting-point policy so a fleet can
be adopted, then edited. Pure: the mixin collects the facts (installed driver-backed apps,
schedules, whitelisted settings, active extensions) and this module renders them.

**Secrets never inline**: a sensitive-looking setting key is emitted as a bare
``fromSecret: {vault, key}`` ref with the live value withheld — the operator stores the real
value in the vault (or opts into ``generate: true`` for a fresh one). Scaffold deliberately
does not set ``generate`` itself: applying a scaffold must never silently rotate a live
credential.
"""
import re

from devicekit.policy.spec import dump_policy_yaml, normalize_policy

SENSITIVE_KEY_RE = re.compile(
    r"(pass(word)?|secret|token|pin|credential|api_?key|psk|auth)", re.IGNORECASE)

# The placeholder vault slug redacted refs point at; created by the operator.
SCAFFOLD_VAULT_SLUG = "fleet-secrets"

# Curated, broadly-safe capture set — ``settings list`` would dump hundreds of noisy,
# often OEM-specific keys. Extend the policy by hand after adoption.
SCAFFOLD_SETTINGS = {
    "system": ["screen_brightness", "screen_off_timeout", "accelerometer_rotation"],
    "global": ["stay_on_while_plugged_in", "adb_enabled"],
    "secure": [],
}


def render_scaffold(device_id, facts, name=None):
    """Facts → validated spec + YAML + redaction report.

    Runs the result through ``normalize_policy`` so a scaffold is guaranteed loadable —
    adopting a device and planning immediately should yield an empty plan."""
    redactions = []
    settings = {}
    for ns, kv in (facts.get("settings") or {}).items():
        for key, value in kv.items():
            if value is None:
                continue
            if SENSITIVE_KEY_RE.search(key):
                secret_key = re.sub(r"[^A-Za-z0-9]+", "_", key).upper()
                settings.setdefault(ns, {})[key] = {
                    "fromSecret": {"vault": SCAFFOLD_VAULT_SLUG, "key": secret_key}}
                redactions.append({
                    "namespace": ns, "key": key, "secret_key": secret_key,
                    "note": f"value withheld — store it in vault "
                            f"'{SCAFFOLD_VAULT_SLUG}' as {secret_key}, or set "
                            f"generate: true to mint a new one"})
            else:
                settings.setdefault(ns, {})[key] = value
    doc = {
        "version": 1,
        "name": name or f"scaffold-{device_id}",
        "target": {"device": device_id},
    }
    if facts.get("apps"):
        doc["apps"] = facts["apps"]
    if facts.get("automations"):
        doc["automations"] = facts["automations"]
    if settings:
        doc["settings"] = settings
    if facts.get("extensions"):
        doc["extensions"] = sorted(facts["extensions"])
    spec = normalize_policy(doc)
    return {"spec": spec, "yaml": dump_policy_yaml(spec), "redactions": redactions}
