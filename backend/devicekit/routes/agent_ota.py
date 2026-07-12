"""OTA agent-update endpoints (plan 25 part 3).

Operator side: upload signed releases, open/observe/rollback rollouts. Agent side (HMAC-gated
when enrolled): pull an update on the rollout policy and report install progress. The APK
download is public bytes whose integrity is guaranteed by the signed manifest's sha256, so it
needs no per-request auth beyond being served over the same channel.
"""
import base64
import logging

from flask import Blueprint, jsonify, request, Response

logger = logging.getLogger(__name__)


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr


def make_blueprint(client, limiter):
    bp = Blueprint('agent_ota', __name__)

    def _require_agent_auth(device_id):
        """HMAC gate for an enrolled device (mirrors agent_devices.py). Returns an error
        response to short-circuit, or None to proceed."""
        try:
            from config import AGENT_ENROLLMENT_REQUIRED
        except Exception:
            AGENT_ENROLLMENT_REQUIRED = False
        creds = client.get_agent_secret(device_id) if device_id else None
        enrolled = bool(creds and creds.get('secret'))
        if not enrolled:
            if AGENT_ENROLLMENT_REQUIRED:
                return jsonify({'error': 'device not enrolled'}), 403
            return None
        ts = request.headers.get('X-Agent-Timestamp', '')
        nonce = request.headers.get('X-Agent-Nonce', '')
        sig = request.headers.get('X-Agent-Signature', '')
        ok, err = client.verify_agent_request(device_id, ts, nonce, sig, ip=_client_ip())
        if not ok:
            return jsonify({'error': err}), 401
        return None

    # ---------------------------------------------------------------- releases
    @bp.route('/agent-device/ota/pubkey')
    def ota_pubkey():
        """The Ed25519 public key an agent pins to verify release manifests."""
        return jsonify({'public_key': client.ota_public_key(), 'algorithm': 'ed25519'})

    @bp.route('/agent-device/ota/releases', methods=['GET'])
    def ota_list_releases():
        rels = client.list_agent_releases()
        return jsonify({'releases': rels, 'count': len(rels)})

    @bp.route('/agent-device/ota/releases', methods=['POST'])
    def ota_create_release():
        """Register a signed release. Accepts a multipart ``apk`` file, or JSON with
        ``apk_b64``. Version metadata via form fields or JSON body."""
        apk_bytes = None
        filename = None
        if request.files.get('apk'):
            f = request.files['apk']
            apk_bytes = f.read()
            filename = f.filename
            data = request.form
        else:
            data = request.get_json(silent=True) or {}
            b64 = data.get('apk_b64')
            if b64:
                try:
                    apk_bytes = base64.b64decode(b64)
                except Exception:
                    return jsonify({'error': 'apk_b64 is not valid base64'}), 400
            filename = data.get('filename')
        if not apk_bytes:
            return jsonify({'error': 'apk file or apk_b64 required'}), 400
        try:
            rel = client.create_agent_release(
                apk_bytes,
                version_name=data.get('version_name'),
                version_code=data.get('version_code'),
                notes=data.get('notes'),
                filename=filename)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(rel), 201

    @bp.route('/agent-device/ota/releases/<release_id>')
    def ota_get_release(release_id):
        rel = client.get_agent_release(release_id)
        if not rel:
            return jsonify({'error': 'release not found'}), 404
        return jsonify(rel)

    @bp.route('/agent-device/ota/releases/<release_id>/yank', methods=['POST'])
    def ota_yank_release(release_id):
        rel = client.yank_agent_release(release_id)
        if not rel:
            return jsonify({'error': 'release not found'}), 404
        return jsonify(rel)

    @bp.route('/agent-device/ota/releases/<release_id>/apk')
    def ota_download_apk(release_id):
        """Serve the signed APK bytes (agent-pull). Integrity is the manifest's signed sha256."""
        data, name = client.get_release_apk(release_id)
        if data is None:
            return jsonify({'error': 'release apk not found'}), 404
        return Response(
            data, mimetype='application/vnd.android.package-archive',
            headers={'Content-Disposition': f'attachment; filename="{name}"',
                     'Content-Length': str(len(data))})

    # ---------------------------------------------------------------- rollouts
    @bp.route('/agent-device/ota/rollouts', methods=['GET'])
    def ota_list_rollouts():
        status = request.args.get('status')
        rollouts = client.list_agent_rollouts(status=status)
        return jsonify({'rollouts': rollouts, 'count': len(rollouts)})

    @bp.route('/agent-device/ota/rollouts', methods=['POST'])
    def ota_create_rollout():
        data = request.get_json(silent=True) or {}
        if not data.get('release_id'):
            return jsonify({'error': 'release_id required'}), 400
        try:
            rollout = client.create_agent_rollout(
                data['release_id'],
                target_kind=data.get('target_kind', 'all'),
                target_value=data.get('target_value'),
                config=data.get('config'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(rollout), 201

    @bp.route('/agent-device/ota/rollouts/<rollout_id>')
    def ota_get_rollout(rollout_id):
        rollout = client.get_agent_rollout(rollout_id)
        if not rollout:
            return jsonify({'error': 'rollout not found'}), 404
        return jsonify(rollout)

    @bp.route('/agent-device/ota/rollouts/<rollout_id>/rollback', methods=['POST'])
    def ota_rollback_rollout(rollout_id):
        data = request.get_json(silent=True) or {}
        result = client.rollback_rollout(rollout_id, reason=data.get('reason'))
        if result is None:
            return jsonify({'error': 'rollout not found'}), 404
        return jsonify(result)

    @bp.route('/agent-device/ota/rollouts/<rollout_id>/pause', methods=['POST'])
    def ota_pause_rollout(rollout_id):
        data = request.get_json(silent=True) or {}
        result = client.set_rollout_paused(rollout_id, bool(data.get('paused', True)))
        if result is None:
            return jsonify({'error': 'rollout not found or already terminal'}), 404
        return jsonify(result)

    # ---------------------------------------------------------------- agent pull
    @bp.route('/agent-device/<device_id>/update-check')
    def ota_update_check(device_id):
        """Agent-pull: does an active rollout offer this device an update right now?"""
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        return jsonify(client.check_device_update(device_id))

    @bp.route('/agent-device/<device_id>/update-status', methods=['POST'])
    def ota_update_status(device_id):
        """Agent reports install progress (downloading/installing/installed/failed)."""
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        data = request.get_json(silent=True) or {}
        rollout_id = data.get('rollout_id')
        status = data.get('status')
        if not rollout_id or not status:
            return jsonify({'error': 'rollout_id and status required'}), 400
        out = client.report_device_update(
            device_id, rollout_id, status,
            version_code=data.get('version_code'), error=data.get('error'))
        return jsonify(out)

    return bp
