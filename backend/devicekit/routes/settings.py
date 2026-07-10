"""Durable app-settings routes (plan 12).

``GET /settings`` returns the full settings object (every declared key, with secret values
redacted to booleans); ``PUT /settings`` merges a flat ``{key: value}`` map and returns the
refreshed object. The pre-existing in-memory ``/config`` blueprint is left untouched for
backward compatibility; ``/settings`` is the durable, schema-backed store.
"""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('settings', __name__)

    @bp.route('/settings')
    def settings_get():
        return jsonify({'settings': client.get_all_settings()})

    @bp.route('/settings', methods=['PUT'])
    def settings_update():
        data = request.get_json(silent=True) or {}
        try:
            settings = client.update_settings(data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify({'settings': settings})

    return bp
