"""Device listing, detail, onboarding, agent APK status, and proxy routes."""
import time

import requests
from bs4 import BeautifulSoup
import logging
from flask import Blueprint, jsonify, request, Response

logger = logging.getLogger(__name__)


def make_blueprint(client, limiter):
    bp = Blueprint('devices', __name__)

    @bp.route('/devices')
    def devices():
        # Refresh device list from ADB on each request
        try:
            adb_devices = client.get_connected_devices()
            for device_id in adb_devices:
                if device_id not in client.devices:
                    try:
                        client.get_device(device_id)
                        # Auto-onboard: ensure agent APK is installed on new devices
                        try:
                            result = client.ensure_agent_installed(device_id)
                            logger.info(f"Auto-onboard {device_id}: {result.get('action')}")
                        except Exception as e:
                            logger.warning(f"Auto-onboard failed for {device_id}: {e}")
                    except Exception as e:
                        logger.warning(f"Could not connect to {device_id}: {e}")
        except Exception as e:
            logger.warning(f"Device refresh failed: {e}")

        connected = client.get_devices()
        adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}

        # ADB-listed devices are connected by definition; when the same device is also
        # agent-registered, fold in the agent's last-reported metrics and model info so
        # the dashboard shows CPU/battery for live devices too (the agent-merge loop
        # below skips ids already present in the ADB list).
        for d in connected:
            if not d:
                continue
            d['online'] = True
            agent = client.find_agent_device(d.get('serial') or d.get('device_id') or '')
            if not agent:
                continue
            info = agent.get('info') or {}
            metrics = (agent.get('state') or {}).get('metrics') or {}
            if not d.get('model') and info.get('model'):
                d['model'] = info['model']
            for src_key, dst_key in (
                ('battery_level', 'battery_level'),
                ('cpu_percent', 'cpu_percent'),
                ('ram_used_mb', 'ram_used_mb'),
                ('ram_total_mb', 'ram_total_mb'),
            ):
                if d.get(dst_key) is None and metrics.get(src_key) is not None:
                    d[dst_key] = metrics[src_key]

        # Merge agent-registered devices that aren't already in the ADB list
        now = time.time()
        for agent_id, agent_data in client._agent_device_states.items():
            if agent_id in adb_ids:
                continue
            info = agent_data.get('info', {})
            state = agent_data.get('state', {})
            metrics = state.get('metrics', {})
            last_hb = agent_data.get('last_heartbeat', 0)
            online = (now - last_hb) < 15 if last_hb else False
            connected.append({
                'serial': agent_id,
                'device_id': agent_id,
                'model': info.get('model', 'Unknown'),
                'manufacturer': info.get('manufacturer', 'Unknown'),
                'brand': info.get('brand', ''),
                'android_version': info.get('android_version', ''),
                'sdk': info.get('sdk', 0),
                'online': online,
                'source': 'agent',
                'agent_version': info.get('agent_version', ''),
                'battery_level': metrics.get('battery_level'),
                'cpu_percent': metrics.get('cpu_percent'),
                'ram_used_mb': metrics.get('ram_used_mb'),
                'ram_total_mb': metrics.get('ram_total_mb'),
                'currentPackageName': state.get('window', {}).get('package'),
                'capabilities': agent_data.get('capabilities', {}),
            })

        return jsonify({'devices': connected, 'count': len(connected)})

    @bp.route('/devices/<device_id>')
    def device_info(device_id):
        info = client.get_device_info(device_id)
        if info:
            return jsonify(info)
        return jsonify({'error': 'Device not found'}), 404

    @bp.route('/devices/<device_id>/onboard', methods=['POST'])
    def device_onboard(device_id):
        """Manually trigger agent APK onboarding for a device."""
        try:
            result = client.ensure_agent_installed(device_id)
            client.log_activity('manual_onboard', device_id, result)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/agent-apk/status')
    def agent_apk_status():
        """Check cached APK version and latest release info."""
        try:
            status = client.get_agent_apk_cache_status()
            return jsonify(status)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/proxy/device/<device_id>')
    def proxy_device(device_id):
        url = f'https://uiauto.dev/android/{device_id}'
        try:
            resp = requests.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            nav = soup.select_one('.p-tabview-nav-content')
            if nav:
                nav['style'] = 'display: none;'
            return Response(str(soup), content_type=resp.headers.get('content-type', 'text/html'))
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    return bp
