"""Agent-plugin manifest: JSON-Schema (Draft 7) validate + normalize (plan 25 part 5).

The manifest is a *contract*, ported from ServerKit's ``agent_plugin.py``: a plugin declares
its ``capabilities`` (what it offers — metrics / health_checks / commands / scheduled_tasks /
event_hooks), its **typed permissions** (what it may touch — filesystem / network / process /
system), its ``resources`` budget (max_memory_mb / max_cpu_percent), and its ``dependencies``
(a plugin-name graph). Validation is the whole deliverable here — nothing executes on a device
yet (``install`` is a documented stub).

Semantic checks the JSON-Schema can't express (a filesystem permission's mode, sane resource
bounds) run after structural validation, and both funnel into a single ``AgentPluginError``
carrying every message at once — the same "collect all errors" shape plan 23 uses.
"""
from jsonschema import Draft7Validator

PLUGIN_MANIFEST_VERSION = 1

_CAPABILITIES = {
    "type": "object",
    "properties": {
        "metrics": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1},
                           "unit": {"type": "string"},
                           "interval_seconds": {"type": "integer", "minimum": 1}},
            "required": ["name"], "additionalProperties": False}},
        "health_checks": {"type": "array", "items": {
            "type": "object",
            "properties": {"key": {"type": "string", "minLength": 1},
                           "title": {"type": "string"}},
            "required": ["key"], "additionalProperties": False}},
        "commands": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1},
                           "description": {"type": "string"}},
            "required": ["name"], "additionalProperties": False}},
        "scheduled_tasks": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1},
                           "schedule": {"type": "string", "minLength": 1}},
            "required": ["name", "schedule"], "additionalProperties": False}},
        "event_hooks": {"type": "array", "items": {
            "type": "object",
            "properties": {"event": {"type": "string", "minLength": 1},
                           "handler": {"type": "string"}},
            "required": ["event"], "additionalProperties": False}},
    },
    "additionalProperties": False,
}

_PERMISSIONS = {
    "type": "object",
    "properties": {
        "filesystem": {"type": "array", "items": {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1},
                           "mode": {"enum": ["read", "write"]}},
            "required": ["path", "mode"], "additionalProperties": False}},
        "network": {"type": "array", "items": {
            "type": "object",
            "properties": {"host": {"type": "string", "minLength": 1},
                           "ports": {"type": "array", "items": {"type": "integer"}}},
            "required": ["host"], "additionalProperties": False}},
        "process": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "system": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
    "additionalProperties": False,
}

MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1,
                 "pattern": r"^[a-z0-9][a-z0-9._-]*$"},
        "version": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "capabilities": _CAPABILITIES,
        "permissions": _PERMISSIONS,
        "resources": {
            "type": "object",
            "properties": {
                "max_memory_mb": {"type": "integer", "minimum": 1},
                "max_cpu_percent": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        "dependencies": {"type": "array",
                         "items": {"type": "string", "minLength": 1}},
    },
    "required": ["name", "version"],
    "additionalProperties": False,
}

_EMPTY_CAPABILITIES = {"metrics": [], "health_checks": [], "commands": [],
                       "scheduled_tasks": [], "event_hooks": []}
_EMPTY_PERMISSIONS = {"filesystem": [], "network": [], "process": [], "system": []}


class AgentPluginError(ValueError):
    """Raised when a manifest is invalid. ``errors`` carries every message at once."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(self.errors))


def validate_plugin_manifest(manifest):
    """Validate + normalize a manifest. Returns a normalized dict with every section present
    (empty lists where omitted) so downstream code never special-cases missing keys. Raises
    ``AgentPluginError`` with all structural + semantic errors collected."""
    if not isinstance(manifest, dict):
        raise AgentPluginError("manifest must be an object")

    errors = [f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
              for e in sorted(Draft7Validator(MANIFEST_SCHEMA).iter_errors(manifest),
                              key=lambda e: list(e.path))]

    # Semantic checks beyond the schema.
    deps = manifest.get("dependencies") or []
    if len(deps) != len(set(deps)):
        errors.append("dependencies: duplicate entries")
    if manifest.get("name") in deps:
        errors.append("dependencies: a plugin cannot depend on itself")

    if errors:
        raise AgentPluginError(errors)

    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest.get("description", ""),
        "capabilities": {**_EMPTY_CAPABILITIES, **(manifest.get("capabilities") or {})},
        "permissions": {**_EMPTY_PERMISSIONS, **(manifest.get("permissions") or {})},
        "resources": manifest.get("resources") or {},
        "dependencies": list(deps),
    }
