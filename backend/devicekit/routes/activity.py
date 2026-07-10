"""Activity routes."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('activity', __name__)

    @bp.route('/activities')
    def activities_list():
        device_id = request.args.get('device_id')
        limit = int(request.args.get('limit', 50))
        activities = client.get_activities(limit=limit, device_id_filter=device_id)
        return jsonify({'activities': activities, 'count': len(activities)})

    return bp
