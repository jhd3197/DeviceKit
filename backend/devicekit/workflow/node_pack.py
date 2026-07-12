"""The DeviceKit node pack — tramo ``NodeDefinition``s generated from the plan-15
step-type registry (core + extension-contributed), served to the editor the same way
tramo folds in MCP servers (``mcpServerToNodeDefs``).

Field mapping is mechanical: DeviceKit step params ``{type: text|number|select, label,
required, default, options}`` are already a subset of tramo ``NodeField``. Every step
node additionally gets the engine-level fields (``device_id`` override, ``critical``,
``store_as``) so the inspector exposes the full run contract.
"""

#: Step categories → lucide icons for the picker/canvas.
_CATEGORY_ICONS = {
    "Interaction": "Pointer",
    "Apps": "LayoutGrid",
    "Timing": "Clock",
    "Debug": "Bug",
    "Visual": "Eye",
    "Control": "ShieldCheck",
}

_DEVICEKIT_COLOR = "#10b981"   # emerald — matches the app accent

#: tramo builtins the Python engine executes today. Served alongside the pack so the
#: editor can grey out builtins the backend would skip at runtime.
SUPPORTED_BUILTINS = [
    "manual-trigger", "webhook-trigger", "cron-trigger",
    "if", "switch", "merge", "for-each", "call-flow",
    "flow-input", "flow-output", "set-var",
    "dk.event-trigger", "dk.device-fan-out",
]


def device_fan_out_node_def():
    """Run a sub-automation across many devices — one concurrency-capped job per
    device branch, per-device timeout, results collected into the parent run."""
    return {
        "id": "dk.device-fan-out",
        "name": "Run Across Devices",
        "category": "action",
        "description": "Fan a sub-automation out over a device list or FQL result — "
                       "one job per device, concurrency-capped, per-device timeout.",
        "icon": "Network",
        "color": "#10b981",
        "integrationId": "devicekit",
        "operationName": "Run Across Devices",
        "inputs": [{"key": "in", "label": "In", "type": "any"}],
        "outputs": [
            {"key": "out", "label": "Results", "type": "object"},
            {"key": "error", "label": "Error", "type": "object"},
        ],
        "fields": [
            {"key": "automation_id", "type": "flow-ref", "label": "Automation",
             "help": "The sub-automation each device branch runs."},
            {"key": "devices", "type": "text", "label": "Devices", "optional": True,
             "help": "Comma-separated serials, a JSON list, or an expression "
                     "(e.g. trigger.devices). Leave empty to target by FQL."},
            {"key": "fql", "type": "text", "label": "FQL query", "optional": True,
             "help": "Fleet query selecting target devices "
                     "(e.g. online = true and battery_level > 30)."},
            {"key": "inputs", "type": "json", "label": "Branch inputs (JSON)",
             "optional": True, "default": "{}",
             "help": "Passed to every branch as {{trigger.*}}. Supports {{var}}s."},
            {"key": "concurrency", "type": "number", "label": "Concurrency",
             "optional": True, "default": 3,
             "help": "Max device branches in flight at once."},
            {"key": "timeout_seconds", "type": "number", "label": "Per-device timeout (s)",
             "optional": True, "default": 600,
             "help": "A branch still running after this is cancelled and marked "
                     "timeout — one slow device never stalls the run."},
        ],
        "group": "Fleet",
    }


def event_trigger_node_def(event_keys=None):
    """The DeviceKit-pack event trigger — starts a run from a plan-06 bus event
    (device.offline, device.battery.critical, automation.run.failed, …)."""
    field = {"key": "event_key", "label": "Event", "optional": False,
             "help": "Notification-bus event that starts this automation."}
    if event_keys:
        field.update({"type": "select",
                      "options": [{"label": k, "value": k} for k in sorted(event_keys)]})
    else:
        field["type"] = "text"
    return {
        "id": "dk.event-trigger",
        "name": "Event Trigger",
        "category": "trigger",
        "description": "Starts the workflow when a DeviceKit event fires "
                       "(device offline, low battery, run failed, …).",
        "icon": "Zap",
        "color": "#8b5cf6",
        "integrationId": "devicekit",
        "operationName": "Event Trigger",
        "inputs": [],
        "outputs": [{"key": "out", "label": "Event", "type": "object"}],
        "fields": [
            field,
            {"key": "cooldown_seconds", "type": "number", "label": "Cooldown (s)",
             "optional": True, "default": 60,
             "help": "Minimum seconds between runs started by this event "
                     "(prevents notification storms)."},
        ],
        "group": "Triggers",
    }


def _field_from_param(key, schema):
    field = {
        "key": key,
        "type": schema.get("type", "text"),
        "label": schema.get("label", key),
        "optional": not schema.get("required", False),
    }
    if "default" in schema:
        field["default"] = schema["default"]
    options = schema.get("options")
    if options:
        field["options"] = [{"label": str(o), "value": str(o)} for o in options]
    return field


def _common_fields():
    return [
        {"key": "device_id", "type": "text", "label": "Device override",
         "optional": True,
         "help": "Serial/id to run this step on. Empty = the run's device."},
        {"key": "critical", "type": "boolean", "label": "Critical",
         "optional": True, "default": False,
         "help": "When on, a failure of this node aborts the whole run "
                 "(instead of flowing to error branches)."},
        {"key": "store_as", "type": "text", "label": "Store output as",
         "optional": True,
         "help": "Variable name for this step's output — reference it later as "
                 "{{vars.name}} (structured outputs also flatten to name_key)."},
    ]


def step_type_to_node_def(type_name, spec):
    """One step-type registry entry → one tramo NodeDefinition (id ``dk.<type>``)."""
    fields = [_field_from_param(key, schema)
              for key, schema in (spec.get("config") or {}).items()]
    fields.extend(_common_fields())
    return {
        "id": f"dk.{type_name}",
        "name": spec.get("label", type_name),
        "category": "action",
        "description": f"DeviceKit step: {spec.get('label', type_name)}",
        "icon": _CATEGORY_ICONS.get(spec.get("category", ""), "Smartphone"),
        "color": _DEVICEKIT_COLOR,
        "integrationId": "devicekit",
        "operationName": spec.get("label", type_name),
        "inputs": [{"key": "in", "label": "In", "type": "any"}],
        "outputs": [{"key": "out", "label": "Output", "type": "any"}],
        "fields": fields,
        # Non-tramo extra: the picker groups DeviceKit ops by their step category.
        "group": spec.get("category", "Other"),
    }


def build_node_pack(step_types, event_keys=None):
    """The full pack payload for ``GET /automations/node-pack``.

    ``step_types`` is ``client.get_step_types()`` — executor callables already
    stripped. ``event_keys`` (the notification catalog) populates the event-trigger
    select when available."""
    nodes = [step_type_to_node_def(name, spec)
             for name, spec in sorted(step_types.items())]
    nodes.insert(0, device_fan_out_node_def())
    nodes.insert(0, event_trigger_node_def(event_keys))
    return {
        "integration": {
            "id": "devicekit",
            "name": "DeviceKit",
            "description": "Device steps from the step-type registry (core + extensions)",
            "icon": "Smartphone",
            "color": _DEVICEKIT_COLOR,
            "category": "Devices",
        },
        "nodes": nodes,
        "supported_builtins": SUPPORTED_BUILTINS,
        "count": len(nodes),
    }
