"""Device onboarding endpoints (plan 25 part 4).

The formal enrollment lifecycle (``pending → validating → provisioning → ready | failed``)
surfaced for the dashboard: list sessions, inspect one device's ordered progress log, and
manually (re)start onboarding for a device.
"""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('onboarding', __name__)

    @bp.route('/onboarding')
    def onboarding_list():
        state = request.args.get('state')
        sessions = client.list_onboarding_sessions(state=state)
        return jsonify({'sessions': sessions, 'count': len(sessions)})

    @bp.route('/onboarding/<session_id>')
    def onboarding_get(session_id):
        session = client.get_onboarding_session(session_id)
        if not session:
            return jsonify({'error': 'session not found'}), 404
        return jsonify(session)

    @bp.route('/onboarding/<session_id>/restart', methods=['POST'])
    def onboarding_restart(session_id):
        session = client.restart_onboarding(session_id)
        if not session:
            return jsonify({'error': 'session not found'}), 404
        return jsonify(session)

    @bp.route('/agent-device/<device_id>/onboarding')
    def device_onboarding(device_id):
        session = client.get_onboarding_session_for_device(device_id)
        if not session:
            return jsonify({'error': 'no onboarding session for device'}), 404
        return jsonify(session)

    @bp.route('/agent-device/<device_id>/onboard', methods=['POST'])
    def device_onboard(device_id):
        """Start (or return the in-flight) onboarding session for a device."""
        data = request.get_json(silent=True) or {}
        session = client.start_onboarding(
            device_id, serial=data.get('serial'), context=data.get('context'))
        return jsonify(session), 201

    return bp
