"""Visual regression testing routes (baselines + comparison reports)."""
import base64

from flask import Blueprint, jsonify, request, Response


def make_blueprint(client, limiter):
    bp = Blueprint('visual_regression', __name__)

    @bp.route('/automations/<automation_id>/baselines', methods=['GET'])
    def list_baselines(automation_id):
        baselines = client.list_baselines(automation_id)
        return jsonify({'baselines': baselines, 'count': len(baselines)})

    @bp.route('/automations/<automation_id>/baselines', methods=['POST'])
    def create_baseline(automation_id):
        data = request.get_json(silent=True) or {}
        step_index = data.get('step_index', 0)
        device_id = data.get('device_id')
        label = data.get('label')
        mask_regions = data.get('mask_regions')

        if device_id:
            # Capture from device
            try:
                result = client.capture_baseline(
                    automation_id, step_index, device_id,
                    label=label, mask_regions=mask_regions,
                )
                client.log_activity('baseline_capture', device_id, {
                    'automation_id': automation_id,
                    'step_index': step_index,
                    'baseline_id': result['id'],
                })
                return jsonify(result), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        elif data.get('image_b64'):
            # Direct image upload
            try:
                image_data = base64.b64decode(data['image_b64'])
                result = client.create_baseline(
                    automation_id, step_index, image_data,
                    device_model=data.get('device_model'),
                    resolution=data.get('resolution'),
                    label=label,
                    mask_regions=mask_regions,
                )
                return jsonify(result), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        else:
            return jsonify({'error': 'device_id or image_b64 required'}), 400

    @bp.route('/automations/<automation_id>/baselines/<baseline_id>')
    def get_baseline_detail(automation_id, baseline_id):
        baseline = client.get_baseline(baseline_id)
        if not baseline or baseline.get('automation_id') != automation_id:
            return jsonify({'error': 'Baseline not found'}), 404
        return jsonify({k: v for k, v in baseline.items() if k != 'image_b64'})

    @bp.route('/automations/<automation_id>/baselines/<baseline_id>/image')
    def get_baseline_image(automation_id, baseline_id):
        image_data = client.get_baseline_image(baseline_id)
        if image_data is None:
            return jsonify({'error': 'Baseline not found'}), 404
        return Response(image_data, mimetype='image/jpeg')

    @bp.route('/automations/<automation_id>/baselines/<baseline_id>', methods=['PUT'])
    def update_baseline(automation_id, baseline_id):
        data = request.get_json(silent=True) or {}
        image_data = None
        if data.get('image_b64'):
            image_data = base64.b64decode(data['image_b64'])
        elif data.get('device_id'):
            try:
                image_data = client.take_screenshot(data['device_id'])
            except Exception:
                pass
        result = client.update_baseline(
            baseline_id,
            image_data=image_data,
            mask_regions=data.get('mask_regions'),
            label=data.get('label'),
        )
        if result is None:
            return jsonify({'error': 'Baseline not found'}), 404
        return jsonify(result)

    @bp.route('/automations/<automation_id>/baselines/<baseline_id>', methods=['DELETE'])
    def delete_baseline(automation_id, baseline_id):
        if client.delete_baseline(baseline_id):
            return '', 204
        return jsonify({'error': 'Baseline not found'}), 404

    @bp.route('/automations/<automation_id>/baselines/<baseline_id>/compare', methods=['POST'])
    def compare_baseline(automation_id, baseline_id):
        """Compare a device's current screenshot against a baseline."""
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        threshold = float(data.get('threshold', 95))
        use_ai = data.get('use_ai', True)

        if not device_id:
            return jsonify({'error': 'device_id required'}), 400

        try:
            screenshot_data = client.take_screenshot(device_id)
            if not screenshot_data:
                return jsonify({'error': 'Failed to capture screenshot'}), 500

            result = client.compare_screenshot(
                screenshot_data, baseline_id=baseline_id,
                threshold=threshold, use_ai=use_ai, device_id=device_id,
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/runs/<run_id>/regression-report')
    def regression_report(run_id):
        report = client.generate_regression_report(run_id)
        if report is None:
            return jsonify({'error': 'Run not found'}), 404
        return jsonify(report)

    return bp
