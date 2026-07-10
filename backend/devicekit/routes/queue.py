"""Queue routes."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('queue', __name__)

    @bp.route('/queue/status')
    def queue_status():
        return jsonify(client.get_all_queue_status())

    @bp.route('/queue/<name>/send', methods=['POST'])
    def queue_send(name):
        data = request.get_json(silent=True) or {}
        body = data.get('body', data)
        msg_id = client.send_message(name, body)
        return jsonify({'message_id': msg_id})

    @bp.route('/queue/<name>/receive', methods=['POST'])
    def queue_receive(name):
        msg = client.receive_message(name)
        if msg:
            return jsonify(msg)
        return jsonify({'message': None}), 204

    return bp
