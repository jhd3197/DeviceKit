"""Config routes."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('config', __name__)

    @bp.route('/config')
    def config_get():
        return jsonify(client._config)

    @bp.route('/config', methods=['PUT'])
    def config_update():
        data = request.get_json(silent=True) or {}
        client._config.update(data)
        return jsonify(client._config)

    return bp
