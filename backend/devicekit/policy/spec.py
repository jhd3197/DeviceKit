"""``devicekit.yaml`` spec: parse, JSON-Schema (Draft 7) validate, normalize, hash (plan 23 part 1).

The manifest declares desired state per device / group / FQL selection. Canonical keys are
camelCase; snake_case aliases are accepted on input and rewritten before validation, so the
schema (and everything downstream — hashing, diffing, storage) only ever sees one shape.

The normalized dict is *stable*: list sections are sorted by their identity key and every
section is always present, so ``policy_hash`` is insensitive to YAML reordering, aliasing,
and omitted-empty sections. The hash is the idempotence primitive: an unchanged hash
short-circuits apply (part 4).

Secrets are never inline — a setting value may be a ``{fromSecret: {vault, key}}`` ref
(plan 20 vault), optionally with ``generate: true`` to mint + store the value on first apply.
"""
import copy
import hashlib
import json

import yaml
from jsonschema import Draft7Validator

POLICY_VERSION = 1

# Android settings namespaces reachable via `adb shell settings put <ns> <key> <value>`.
SETTINGS_NAMESPACES = ("system", "global", "secure")

_SECRET_REF = {
    "type": "object",
    "properties": {
        "fromSecret": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "minLength": 1},
                "key": {"type": "string", "minLength": 1},
            },
            "required": ["vault", "key"],
            "additionalProperties": False,
        },
        "generate": {"type": "boolean"},
    },
    "required": ["fromSecret"],
    "additionalProperties": False,
}

_SETTING_VALUE = {"oneOf": [
    {"type": ["string", "number", "boolean"]},
    _SECRET_REF,
]}

_SETTINGS_SECTION = {
    "type": "object",
    "properties": {ns: {
        "type": "object",
        "additionalProperties": _SETTING_VALUE,
    } for ns in SETTINGS_NAMESPACES},
    "additionalProperties": False,
}

_APP_ENTRY = {
    "type": "object",
    "properties": {
        "package": {"type": "string", "minLength": 1},
        "version": {"type": ["string", "number"]},
        # Owning app-driver extension (plan 18) — the only provisioning path. Without it a
        # missing/mismatched app is a blocker, not an installable step.
        "extension": {"type": "string", "minLength": 1},
    },
    "required": ["package"],
    "additionalProperties": False,
}

_AUTOMATION_ENTRY = {
    "type": "object",
    "properties": {
        # Automation id or exact name — resolved at plan time.
        "automation": {"type": "string", "minLength": 1},
        "enabled": {"type": "boolean"},
        "schedule": {
            "type": "object",
            "properties": {"intervalMinutes": {"type": "integer", "minimum": 1}},
            "required": ["intervalMinutes"],
            "additionalProperties": False,
        },
    },
    "required": ["automation", "schedule"],
    "additionalProperties": False,
}

_SECTION_PROPS = {
    "apps": {"type": "array", "items": _APP_ENTRY},
    "automations": {"type": "array", "items": _AUTOMATION_ENTRY},
    "settings": _SETTINGS_SECTION,
    "extensions": {"type": "array", "items": {"type": "string", "minLength": 1}},
}

POLICY_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "devicekit.yaml",
    "type": "object",
    "properties": {
        "version": {"const": POLICY_VERSION},
        "name": {"type": "string"},
        "target": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "minLength": 1},
                "group": {"type": "string", "minLength": 1},
                "fql": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
            "minProperties": 1,
            "maxProperties": 1,
        },
        "autoApply": {"type": "boolean"},
        **_SECTION_PROPS,
        # Per-device overrides for group/FQL targets (merge-by-key, see
        # ``effective_spec_for_device``). No deeper inheritance in v1.
        "overrides": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": _SECTION_PROPS,
                "additionalProperties": False,
            },
        },
    },
    "required": ["version", "target"],
    "additionalProperties": False,
}

_VALIDATOR = Draft7Validator(POLICY_SCHEMA)


class PolicySpecError(ValueError):
    """Raised when a policy fails to parse or validate. ``errors`` lists every problem."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# ---------------------------------------------------------------------------
# Aliasing (snake_case input → camelCase canonical)
# ---------------------------------------------------------------------------

def _alias_setting_value(value):
    if isinstance(value, dict) and "from_secret" in value and "fromSecret" not in value:
        value = dict(value)
        value["fromSecret"] = value.pop("from_secret")
    return value


def _alias_sections(section_map):
    """Rewrite snake_case aliases inside one {apps, automations, settings, extensions} bag.

    Aliasing is targeted at known levels rather than a blind recursive rename, so a device
    *setting* literally named ``interval_minutes`` is never mangled.
    """
    out = dict(section_map)
    autos = out.get("automations")
    if isinstance(autos, list):
        fixed = []
        for entry in autos:
            if isinstance(entry, dict):
                entry = dict(entry)
                sched = entry.get("schedule")
                if isinstance(sched, dict) and "interval_minutes" in sched \
                        and "intervalMinutes" not in sched:
                    sched = dict(sched)
                    sched["intervalMinutes"] = sched.pop("interval_minutes")
                    entry["schedule"] = sched
            fixed.append(entry)
        out["automations"] = fixed
    settings = out.get("settings")
    if isinstance(settings, dict):
        out["settings"] = {
            ns: ({k: _alias_setting_value(v) for k, v in kv.items()}
                 if isinstance(kv, dict) else kv)
            for ns, kv in settings.items()
        }
    return out


def _apply_aliases(doc):
    doc = dict(doc)
    if "auto_apply" in doc and "autoApply" not in doc:
        doc["autoApply"] = doc.pop("auto_apply")
    doc = _alias_sections(doc)
    overrides = doc.get("overrides")
    if isinstance(overrides, dict):
        doc["overrides"] = {
            device_id: (_alias_sections(o) if isinstance(o, dict) else o)
            for device_id, o in overrides.items()
        }
    return doc


# ---------------------------------------------------------------------------
# Normalize + hash
# ---------------------------------------------------------------------------

def _normalize_sections(bag):
    """Stable-order the list sections and stringify app version pins in one section bag."""
    out = {}
    apps = []
    for entry in bag.get("apps") or []:
        entry = dict(entry)
        if "version" in entry:
            entry["version"] = str(entry["version"])
        apps.append(entry)
    out["apps"] = sorted(apps, key=lambda a: a["package"])
    autos = []
    for entry in bag.get("automations") or []:
        entry = dict(entry)
        entry.setdefault("enabled", True)
        autos.append(entry)
    out["automations"] = sorted(autos, key=lambda a: a["automation"])
    settings = bag.get("settings") or {}
    out["settings"] = {ns: dict(settings[ns]) for ns in SETTINGS_NAMESPACES
                       if isinstance(settings.get(ns), dict) and settings[ns]}
    out["extensions"] = sorted(set(bag.get("extensions") or []))
    return out


def normalize_policy(doc):
    """Validate an already-parsed policy dict and return the normalized canonical form.

    Raises ``PolicySpecError`` listing every schema violation (not just the first)."""
    if not isinstance(doc, dict):
        raise PolicySpecError(["policy must be a YAML mapping"])
    doc = _apply_aliases(doc)
    errors = sorted(_VALIDATOR.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        raise PolicySpecError(
            f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors)
    target = doc["target"]
    target_kind = next(iter(target))
    normalized = {
        "version": POLICY_VERSION,
        "name": doc.get("name", ""),
        "target": {target_kind: target[target_kind]},
        "autoApply": bool(doc.get("autoApply", False)),
        **_normalize_sections(doc),
        "overrides": {
            device_id: _normalize_sections(o)
            for device_id, o in sorted((doc.get("overrides") or {}).items())
        },
    }
    return normalized


def load_policy(yaml_text):
    """Parse YAML text → validated, normalized policy dict. The single entry point."""
    if not (yaml_text or "").strip():
        raise PolicySpecError(["policy is empty"])
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise PolicySpecError([f"invalid YAML: {e}"])
    return normalize_policy(doc)


def policy_hash(normalized):
    """sha256 of the canonical JSON dump — the identity used for the idempotent
    unchanged-hash short-circuit (part 4)."""
    canon = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Per-device effective spec (group + override, merge-by-key)
# ---------------------------------------------------------------------------

def effective_spec_for_device(normalized, device_id):
    """Fold a device's override into the base sections.

    Merge semantics (v1, no inheritance trees): apps merge by ``package``, automations by
    ``automation``, settings by namespace+key, extensions union — the override entry wins."""
    base = {k: copy.deepcopy(normalized[k])
            for k in ("apps", "automations", "settings", "extensions")}
    override = (normalized.get("overrides") or {}).get(device_id)
    if not override:
        return base
    merged_apps = {a["package"]: a for a in base["apps"]}
    merged_apps.update({a["package"]: a for a in override.get("apps") or []})
    base["apps"] = sorted(merged_apps.values(), key=lambda a: a["package"])
    merged_autos = {a["automation"]: a for a in base["automations"]}
    merged_autos.update({a["automation"]: a for a in override.get("automations") or []})
    base["automations"] = sorted(merged_autos.values(), key=lambda a: a["automation"])
    for ns, kv in (override.get("settings") or {}).items():
        base["settings"].setdefault(ns, {}).update(kv)
    base["extensions"] = sorted(set(base["extensions"]) | set(override.get("extensions") or []))
    return base


# ---------------------------------------------------------------------------
# YAML rendering (scaffold, part 6)
# ---------------------------------------------------------------------------

def dump_policy_yaml(spec):
    """Render a policy dict as clean YAML (stable key order, no anchors/aliases)."""
    ordered = {}
    for key in ("version", "name", "target", "autoApply", "apps", "automations",
                "settings", "extensions", "overrides"):
        if key in spec and (spec[key] or key in ("version", "target")):
            ordered[key] = spec[key]
    return yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False)
