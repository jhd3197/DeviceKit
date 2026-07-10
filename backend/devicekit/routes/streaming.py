"""Real-time device streaming + session recording routes."""
from flask import Blueprint, jsonify, request, Response


def make_blueprint(client, limiter):
    bp = Blueprint('streaming', __name__)

    @bp.route('/devices/<device_id>/stream')
    def device_stream(device_id):
        fps = request.args.get('fps', 10, type=int)
        quality = request.args.get('quality', 50, type=int)
        result = client.proxy_device_stream(device_id, fps=fps, quality=quality)
        if result is None:
            return jsonify({'error': 'Stream not available for this device'}), 503
        generator, content_type = result
        client.broadcast('stream_viewer', {
            'device_id': device_id,
            'viewers': client.get_stream_viewers(device_id) + 1,
        })

        def on_close_generator():
            try:
                yield from generator
            finally:
                client.broadcast('stream_viewer', {
                    'device_id': device_id,
                    'viewers': max(0, client.get_stream_viewers(device_id)),
                })

        return Response(
            on_close_generator(),
            mimetype=content_type,
            headers={
                'Cache-Control': 'no-cache, no-store',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )

    @bp.route('/devices/<device_id>/stream/status')
    def device_stream_status(device_id):
        viewers = client.get_stream_viewers(device_id)
        available = client.is_stream_available(device_id)
        return jsonify({'viewers': viewers, 'available': available})

    @bp.route('/devices/<device_id>/sessions/record', methods=['POST'])
    def device_stream_record_start(device_id):
        data = request.get_json(silent=True) or {}
        fps = data.get('fps', 10)
        quality = data.get('quality', 50)
        try:
            result = client.start_recording_session(device_id, fps=fps, quality=quality)
            client.log_activity('stream_record_start', device_id, result)
            return jsonify(result), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/sessions/<session_id>/stop', methods=['POST'])
    def device_stream_record_stop(device_id, session_id):
        result = client.stop_recording_session(session_id)
        if result is None:
            return jsonify({'error': 'Recording session not found'}), 404
        client.log_activity('stream_record_stop', device_id, {
            'session_id': session_id,
            'frame_count': result['frame_count'],
            'duration_ms': result['duration_ms'],
        })
        return jsonify(result)

    @bp.route('/devices/<device_id>/sessions')
    def device_stream_sessions(device_id):
        sessions = client.get_recording_sessions(device_id)
        return jsonify({'sessions': sessions, 'count': len(sessions)})

    @bp.route('/devices/<device_id>/sessions/<session_id>')
    def device_stream_session_detail(device_id, session_id):
        meta = client.get_recording_metadata(session_id)
        if meta is None:
            return jsonify({'error': 'Recording session not found'}), 404
        return jsonify(meta)

    @bp.route('/devices/<device_id>/sessions/<session_id>/frames/<int:frame_index>')
    def device_stream_session_frame(device_id, session_id, frame_index):
        data = client.get_recording_frame(session_id, frame_index)
        if data is None:
            return jsonify({'error': 'Frame not found'}), 404
        return Response(data, mimetype='image/jpeg')

    @bp.route('/devices/<device_id>/sessions/<session_id>/events', methods=['POST'])
    def device_stream_session_event(device_id, session_id):
        data = request.get_json(silent=True) or {}
        count = client.record_stream_event(session_id, data)
        if count is None:
            return jsonify({'error': 'Session not found or not active'}), 404
        return jsonify({'count': count})

    return bp
