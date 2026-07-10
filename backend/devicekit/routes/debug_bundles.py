"""Debug bundle routes (generate, list, download, analyze, share)."""
import io
import logging

from flask import Blueprint, jsonify, request, send_file

logger = logging.getLogger(__name__)


def make_blueprint(client, limiter):
    bp = Blueprint('debug_bundles', __name__)

    @bp.route('/devices/<device_id>/debug-bundle', methods=['POST'])
    def generate_debug_bundle(device_id):
        """On-demand debug bundle generation for a device."""
        data = request.get_json(silent=True) or {}
        trigger = data.get('trigger', 'manual')
        context = data.get('context', {})
        try:
            # Run retention cleanup on each manual generation
            client.cleanup_old_bundles()
            bundle = client.generate_debug_bundle(device_id, trigger=trigger, context=context)
            return jsonify(bundle), 201
        except Exception as e:
            logger.error(f"Debug bundle generation failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/debug-bundles')
    def list_debug_bundles():
        """List all debug bundles with optional filters."""
        device_id = request.args.get('device_id')
        trigger = request.args.get('trigger')
        limit = int(request.args.get('limit', 50))
        bundles = client.list_debug_bundles(device_id=device_id, trigger=trigger, limit=limit)
        return jsonify({'bundles': bundles, 'count': len(bundles)})

    @bp.route('/debug-bundles/<bundle_id>')
    def get_debug_bundle(bundle_id):
        """Get debug bundle metadata."""
        bundle = client.get_debug_bundle(bundle_id)
        if not bundle:
            return jsonify({'error': 'Bundle not found'}), 404
        return jsonify(bundle)

    @bp.route('/debug-bundles/<bundle_id>/download')
    def download_debug_bundle(bundle_id):
        """Download debug bundle as ZIP."""
        zip_data = client.get_bundle_zip(bundle_id)
        if not zip_data:
            return jsonify({'error': 'Bundle not found'}), 404
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'debug-bundle-{bundle_id[:8]}.zip',
        )

    @bp.route('/debug-bundles/<bundle_id>/analyze', methods=['POST'])
    def analyze_debug_bundle(bundle_id):
        """Trigger AI analysis of a debug bundle."""
        result = client.analyze_debug_bundle(bundle_id)
        if result is None:
            return jsonify({'error': 'Bundle not found'}), 404
        if result.get('error'):
            return jsonify(result), 500
        return jsonify(result)

    @bp.route('/debug-bundles/<bundle_id>/share', methods=['POST'])
    def share_debug_bundle(bundle_id):
        """Generate a shareable link for a debug bundle."""
        data = request.get_json(silent=True) or {}
        # Default lifetime comes from Settings > Debug Bundles (share-token lifetime),
        # unless the caller pins expires_hours explicitly.
        default_hours = client.share_token_lifetime_minutes() / 60.0
        hours = float(data.get('expires_hours', default_hours))
        result = client.generate_share_link(bundle_id, expires_hours=hours)
        if not result:
            return jsonify({'error': 'Bundle not found'}), 404
        return jsonify(result), 201

    @bp.route('/debug-bundles/share/<token>')
    def download_shared_bundle(token):
        """Download a debug bundle via share token."""
        zip_data, error = client.get_bundle_by_share_token(token)
        if error:
            return jsonify({'error': error}), 403 if 'expired' in error.lower() else 404
        if not zip_data:
            return jsonify({'error': 'Bundle data not available'}), 404
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'debug-bundle-shared.zip',
        )

    @bp.route('/debug-bundles/<bundle_id>', methods=['DELETE'])
    def delete_debug_bundle(bundle_id):
        """Delete a debug bundle."""
        deleted = client.delete_debug_bundle(bundle_id)
        if not deleted:
            return jsonify({'error': 'Bundle not found'}), 404
        return jsonify({'deleted': True})

    return bp
