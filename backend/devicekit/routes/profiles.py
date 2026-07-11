"""Device profile routes."""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('profiles', __name__)

    @bp.route('/profiles')
    def profiles_list():
        profiles = client.list_profiles()
        return jsonify({'profiles': profiles, 'count': len(profiles)})

    @bp.route('/profiles', methods=['POST'])
    def profiles_create():
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        name = data.get('name')
        if not device_id or not name:
            return jsonify({'error': 'device_id and name are required'}), 400
        profile = client.create_profile(
            device_id=device_id,
            name=name,
            personality=data.get('personality', ''),
            niche=data.get('niche', ''),
            interests=data.get('interests', []),
            behavior_patterns=data.get('behavior_patterns'),
            apps=data.get('apps', []),
            model_name=data.get('model_name', ''),
        )
        return jsonify(profile), 201

    @bp.route('/profiles/<profile_id>')
    def profiles_get(profile_id):
        profile = client.get_profile(profile_id)
        if profile:
            return jsonify(profile)
        return jsonify({'error': 'Profile not found'}), 404

    @bp.route('/profiles/device/<device_id>')
    def profiles_by_device(device_id):
        profile = client.get_profile_by_device(device_id)
        if profile:
            return jsonify(profile)
        return jsonify({'error': 'No profile for this device'}), 404

    @bp.route('/profiles/<profile_id>', methods=['PUT'])
    def profiles_update(profile_id):
        data = request.get_json(silent=True) or {}
        result = client.update_profile(profile_id, data)
        if result is None:
            return jsonify({'error': 'Profile not found'}), 404
        return jsonify(result)

    @bp.route('/profiles/<profile_id>', methods=['DELETE'])
    def profiles_delete(profile_id):
        if client.delete_profile(profile_id):
            return '', 204
        return jsonify({'error': 'Profile not found'}), 404

    return bp
