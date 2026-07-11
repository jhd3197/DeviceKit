"""AI agent control routes (Prompture-backed autonomous agent)."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('ai_agent', __name__)

    @bp.route('/agent/status')
    def agent_status_all():
        return jsonify(client.get_all_agent_status())

    @bp.route('/agent/<device_id>/status')
    def agent_status(device_id):
        return jsonify(client.get_agent_status(device_id))

    @bp.route('/agent/<device_id>/start', methods=['POST'])
    def agent_start(device_id):
        profile = client.get_profile_by_device(device_id)
        if not profile:
            return jsonify({'error': 'No profile found for this device. Create a profile first.'}), 400
        model_name = profile.get('model_name', '') or None
        result = client.start_agent(device_id, profile, model_name=model_name)
        if 'error' in result:
            return jsonify(result), 409
        client.log_activity('agent_start', device_id)
        return jsonify(result)

    @bp.route('/agent/<device_id>/stop', methods=['POST'])
    def agent_stop(device_id):
        result = client.stop_agent(device_id)
        client.log_activity('agent_stop', device_id)
        return jsonify(result)

    @bp.route('/agent/<device_id>/command', methods=['POST'])
    def agent_command(device_id):
        data = request.get_json(silent=True) or {}
        command = data.get('command', '')
        if not command:
            return jsonify({'error': 'command is required'}), 400
        priority = data.get('priority', 'normal')
        cmd = client.enqueue_command(device_id, command, priority)
        client.log_activity('agent_command', device_id, {'command': command, 'priority': priority})
        return jsonify(cmd), 201

    @bp.route('/agent/<device_id>/commands')
    def agent_commands(device_id):
        return jsonify({'commands': client.get_command_queue(device_id)})

    @bp.route('/agent/<device_id>/logs')
    def agent_logs(device_id):
        limit = int(request.args.get('limit', 50))
        return jsonify({'logs': client.get_agent_logs(device_id, limit)})

    @bp.route('/devices/<device_id>/conversation/history')
    def conversation_history(device_id):
        messages = client.get_conversation_history(device_id)
        return jsonify({'messages': messages, 'turn_count': len(messages)})

    @bp.route('/devices/<device_id>/conversation', methods=['DELETE'])
    def conversation_clear(device_id):
        result = client.clear_conversation(device_id)
        return jsonify(result)

    @bp.route('/devices/<device_id>/agent/usage')
    def agent_usage(device_id):
        usage = client.get_agent_usage(device_id)
        return jsonify(usage)

    @bp.route('/devices/<device_id>/agent/model', methods=['PATCH'])
    def agent_model_switch(device_id):
        data = request.get_json(silent=True) or {}
        model_name = data.get('model_name', '')
        if not model_name:
            return jsonify({'error': 'model_name is required'}), 400
        result = client.switch_agent_model(device_id, model_name)
        return jsonify(result)

    # ---- Prompture Hub (plan 19) ------------------------------------------------------

    @bp.route('/ai/hub/health')
    def ai_hub_health():
        """Proxy probe of the configured prompture-hub: liveness + key-scoped model
        list. Frontend probes through here so the hub URL stays server-side (no CORS)."""
        return jsonify(client.ai_hub_health())

    # ---- Confirmation gate (plan 13) --------------------------------------------------

    @bp.route('/devices/<device_id>/agent/pending')
    def agent_pending(device_id):
        actions = client.list_pending_actions(device_id)
        return jsonify({'pending_actions': actions, 'count': len(actions)})

    @bp.route('/devices/<device_id>/agent/confirm', methods=['POST'])
    def agent_confirm(device_id):
        data = request.get_json(silent=True) or {}
        action_id = data.get('action_id')
        if not action_id:
            return jsonify({'error': 'action_id is required'}), 400
        approve = bool(data.get('approve', False))
        approver = request.headers.get('X-API-Key', '')[:8] or 'api'
        result = client.confirm_action(action_id, approve, approver=approver,
                                       device_id=device_id)
        if 'error' in result:
            return jsonify(result), 404
        client.log_activity('agent_confirm', device_id,
                            {'action_id': action_id, 'approve': approve})
        return jsonify(result)

    @bp.route('/devices/<device_id>/agent/mode', methods=['GET'])
    def agent_mode_get(device_id):
        return jsonify({'mode': client.get_agent_mode(device_id)})

    @bp.route('/devices/<device_id>/agent/mode', methods=['PUT'])
    def agent_mode_set(device_id):
        data = request.get_json(silent=True) or {}
        mode = data.get('mode', '')
        result = client.set_agent_mode(device_id, mode)
        if 'error' in result:
            return jsonify(result), 400
        client.log_activity('agent_mode', device_id, {'mode': mode})
        return jsonify(result)

    @bp.route('/devices/<device_id>/agent/audit')
    def agent_audit(device_id):
        limit = int(request.args.get('limit', 100))
        entries = client.get_agent_audit(device_id, limit)
        return jsonify({'audit': entries, 'count': len(entries)})

    return bp
