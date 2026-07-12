"""Curated, gated device actions for external callers (plan 21, part 3).

``POST /actions/invoke`` is how a machine (the MCP server, CI, a script) executes a
hardware-touching capability: every write routes through the plan-13 confirmation gate —
the same pending-action → human-approval flow an in-app AI action gets. There is no side
door: a ``dk_`` key without the exact ``mcp:autonomous`` opt-in is **always gated**, even
when the device's agent mode is ``autonomous``; with the opt-in, the device mode decides
(and the auto-approval is audited like any other gate decision).

The action set is deliberately the curated core tool registry (plan 13) plus
``run_automation`` — not raw route parity. Extension-contributed tools are not invocable
here; they stay inside in-app agent conversations where their consent story lives.
"""
from flask import Blueprint, jsonify, request

from devicekit.mixins.prompture_agent import build_device_tools
from devicekit.services.scopes import has_exact_scope, require_scope, scope_allows

# Scope each action class maps to (the registry's is_write flag picks the class).
_READ_SCOPE = "devices:read"
_WRITE_SCOPE = "devices:command"
_RUN_SCOPE = "automations:run"

_RUN_AUTOMATION_ENTRY = {
    "name": "run_automation",
    "description": "Queue an automation run on the device (returns the run record id).",
    "parameters": {
        "type": "object",
        "properties": {"automation_id": {"type": "string"}},
        "required": ["automation_id"],
    },
    "is_write": True,
    "category": "automation",
    "scope": _RUN_SCOPE,
}


def _principal():
    from flask import g
    return getattr(g, "principal", None)


def _force_gate(principal):
    """External keys are always-gated unless they hold the exact autonomous opt-in."""
    scopes = getattr(principal, "scopes", None) if principal is not None else None
    return scopes is not None and not has_exact_scope(scopes, "mcp:autonomous")


def _missing_scope(principal, scope):
    """The route-level authorization for the action classes.

    Scoped ``dk_`` keys check the scope catalog; session/user principals fold the action
    class back onto the plan-20 role matrix (``devices:command`` ⇒ devices write,
    ``automations:run`` ⇒ automations write) — ``/actions`` is not feature-mapped in the
    central gate, so without this a viewer-role user could invoke writes the direct
    routes deny them. No side door around RBAC.
    """
    if principal is None or getattr(principal, "full_access", False):
        return None
    scopes = getattr(principal, "scopes", None)
    if scopes is not None:
        if scope_allows(scopes, scope):
            return None
        return jsonify({"error": f"Missing required scope: {scope}"}), 403
    feature, _, verb = scope.partition(":")
    if principal.can(feature, "read" if verb == "read" else "write"):
        return None
    return jsonify({"error": "Insufficient permissions"}), 403


def make_blueprint(client, limiter):
    bp = Blueprint('actions', __name__)

    @bp.route('/actions')
    @require_scope(_READ_SCOPE)
    def actions_list():
        """List the invocable actions with their JSON schemas and required scopes."""
        registry = build_device_tools(client, "_schema", mode="supervised", source="api")
        actions = []
        for td in registry.definitions:
            meta = td.metadata or {}
            if meta.get("category") == "extension":
                continue
            actions.append({
                "name": td.name,
                "description": td.description,
                "parameters": td.parameters,
                "is_write": bool(meta.get("is_write")),
                "category": meta.get("category"),
                "scope": _WRITE_SCOPE if meta.get("is_write") else _READ_SCOPE,
            })
        actions.append(dict(_RUN_AUTOMATION_ENTRY))
        return jsonify({"actions": actions, "count": len(actions)})

    @bp.route('/actions/invoke', methods=['POST'])
    @limiter.limit("30 per minute")
    def actions_invoke():
        """Invoke one curated action on a device; writes wait on the confirmation gate.

        Body: ``{"device_id": ..., "action": ..., "args": {...}}``. The response's
        ``result`` is the gate's outcome string — a ``DENIED: ...`` prefix means the
        approval was declined, timed out, or the device is in observe mode.
        """
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        action = data.get('action')
        args = data.get('args') or {}
        if not device_id or not action:
            return jsonify({'error': 'device_id and action are required'}), 400
        if not isinstance(args, dict):
            return jsonify({'error': 'args must be an object'}), 400

        principal = _principal()
        force_gate = _force_gate(principal)

        if action == 'run_automation':
            guard = _missing_scope(principal, _RUN_SCOPE)
            if guard:
                return guard
            automation_id = args.get('automation_id')
            if not automation_id:
                return jsonify({'error': 'args.automation_id is required'}), 400

            def run_automation(automation_id):
                run = client.execute_automation(automation_id, device_id)
                return f"Automation queued: run {run.get('id')}"

            meta = {"is_write": True, "category": "automation",
                    "label": f"Run automation {automation_id}"}
            if force_gate:
                meta["always_gate"] = True
            result = client.gate_tool_call(device_id, 'run_automation',
                                           {'automation_id': automation_id}, meta,
                                           'api', run_automation)
        else:
            # mode='supervised' only controls tool *visibility*; the gate itself reads the
            # live device mode, so observe-mode devices still deny writes with a clear string.
            registry = build_device_tools(client, device_id, mode="supervised",
                                          source="api", always_gate_core=force_gate)
            td = registry.get(action)
            if td is None or (td.metadata or {}).get("category") == "extension":
                return jsonify({'error': f'Unknown action: {action}'}), 404
            is_write = bool((td.metadata or {}).get("is_write"))
            guard = _missing_scope(principal, _WRITE_SCOPE if is_write else _READ_SCOPE)
            if guard:
                return guard
            try:
                result = registry.execute(action, args)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        result = str(result)
        status = 'denied' if result.startswith('DENIED') else 'ok'
        return jsonify({'device_id': device_id, 'action': action,
                        'result': result, 'status': status})

    return bp
