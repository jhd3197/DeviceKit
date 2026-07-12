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
]


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


def build_node_pack(step_types):
    """The full pack payload for ``GET /automations/node-pack``.

    ``step_types`` is ``client.get_step_types()`` — executor callables already
    stripped."""
    nodes = [step_type_to_node_def(name, spec)
             for name, spec in sorted(step_types.items())]
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
