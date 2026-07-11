"""Alerts routes."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('alerts', __name__)

    @bp.route('/alerts')
    def alerts_list():
        type_filter = request.args.get('type')
        limit = int(request.args.get('limit', 50))
        alerts = client.get_alerts(limit=limit, type_filter=type_filter)
        return jsonify({'alerts': alerts, 'count': len(alerts)})

    @bp.route('/alerts', methods=['POST'])
    def alerts_create():
        data = request.get_json(silent=True) or {}
        alert = client.create_alert(
            device_id=data.get('device_id', 'unknown'),
            alert_type=data.get('type', 'error'),
            message=data.get('message', ''),
            severity=data.get('severity', 'warning'),
        )
        return jsonify(alert), 201

    @bp.route('/alerts/<alert_id>/dismiss', methods=['PUT'])
    def alerts_dismiss(alert_id):
        if client.dismiss_alert(alert_id):
            return jsonify({'status': 'dismissed'})
        return jsonify({'error': 'Alert not found'}), 404

    return bp
