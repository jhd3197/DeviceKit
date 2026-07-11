"""Device control routes (adb, input, screenshot, diagnostics, files)."""
import time
import requests
import logging
from flask import Blueprint, jsonify, request, Response

logger = logging.getLogger(__name__)


def make_blueprint(client, limiter):
    bp = Blueprint('device_control', __name__)

    @bp.route('/devices/<device_id>/adb', methods=['POST'])
    @limiter.limit("30 per minute")
    def device_adb(device_id):
        data = request.get_json(silent=True) or {}
        command = data.get('command', '')
        if not command:
            return jsonify({'error': 'No command provided'}), 400
        try:
            output = client.run_adb_command(f"shell {command}", device=device_id)
            client.log_activity('adb_command', device_id, {'command': command})
            return jsonify({'output': output, 'device_id': device_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/reboot', methods=['POST'])
    @limiter.limit("5 per minute")
    def device_reboot(device_id):
        try:
            client.reboot_device(device=device_id)
            client.log_activity('reboot', device_id)
            return jsonify({'status': 'rebooting', 'device_id': device_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/screenshot')
    def device_screenshot(device_id):
        try:
            data = client.take_screenshot(device_id)
            if data:
                return Response(data, mimetype='image/png')
            return jsonify({'error': 'Screenshot failed'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/tap', methods=['POST'])
    def device_tap(device_id):
        data = request.get_json(silent=True) or {}
        x = data.get('x')
        y = data.get('y')
        if x is None or y is None:
            return jsonify({'error': 'x and y are required'}), 400
        try:
            client.click(int(x), int(y), device_id)
            client.log_activity('tap', device_id, {'x': x, 'y': y})
            return jsonify({'status': 'ok', 'x': x, 'y': y})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/press', methods=['POST'])
    def device_press(device_id):
        data = request.get_json(silent=True) or {}
        action = data.get('action')
        if not action:
            return jsonify({'error': 'action is required'}), 400
        try:
            client.press_action(action, device_id)
            client.log_activity('press', device_id, {'action': action})
            return jsonify({'status': 'ok', 'action': action})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/swipe', methods=['POST'])
    def device_swipe(device_id):
        data = request.get_json(silent=True) or {}
        duration = int(data.get('duration', 400))
        try:
            d = client.get_device(device_id)
            # Freeform swipe: startX, startY, endX, endY
            if 'startX' in data and 'startY' in data and 'endX' in data and 'endY' in data:
                sx = int(data['startX'])
                sy = int(data['startY'])
                ex = int(data['endX'])
                ey = int(data['endY'])
                d.swipe(sx, sy, ex, ey, duration=duration / 1000)
                client.log_activity('swipe', device_id, {
                    'startX': sx, 'startY': sy, 'endX': ex, 'endY': ey,
                })
                return jsonify({'status': 'ok', 'startX': sx, 'startY': sy, 'endX': ex, 'endY': ey})
            # Directional swipe
            direction = data.get('direction', 'up')
            info = d.info
            w = info.get('displayWidth', 1080)
            h = info.get('displayHeight', 1920)
            cx, cy = w // 2, h // 2
            swipe_map = {
                'up': (cx, h * 3 // 4, cx, h // 4),
                'down': (cx, h // 4, cx, h * 3 // 4),
                'left': (w * 3 // 4, cy, w // 4, cy),
                'right': (w // 4, cy, w * 3 // 4, cy),
            }
            coords = swipe_map.get(direction, swipe_map['up'])
            d.swipe(*coords, duration=duration / 1000)
            client.log_activity('swipe', device_id, {'direction': direction})
            return jsonify({'status': 'ok', 'direction': direction})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/battery')
    def device_battery(device_id):
        try:
            info = client.get_device_battery(device=device_id)
            return jsonify(info)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/diagnostics')
    def device_diagnostics(device_id):
        """Return device diagnostics, preferring agent-sourced metrics when available."""
        try:
            # Check if we have recent agent-sourced metrics (< 10s old)
            agent_data = client.find_agent_device(device_id)
            if agent_data:
                last_hb = agent_data.get('last_heartbeat', 0)
                if time.time() - last_hb < 10:
                    state = agent_data.get('state', {})
                    metrics = state.get('metrics', {})
                    if metrics:
                        network = metrics.get('network', {})
                        return jsonify({
                            'battery_level': metrics.get('battery_level', 0),
                            'temperature': metrics.get('battery_temperature', 0),
                            'cpu_percent': metrics.get('cpu_percent', 0),
                            'mem_total_mb': metrics.get('ram_total_mb', 0),
                            'mem_used_mb': metrics.get('ram_used_mb', 0),
                            'is_charging': metrics.get('is_charging', False),
                            'network_type': network.get('type', 'unknown'),
                            'network_rx_rate': network.get('rx_rate', 0),
                            'network_tx_rate': network.get('tx_rate', 0),
                            'uptime_seconds': 0,
                            'source': 'agent',
                        })

            # Fallback to ADB-sourced diagnostics
            battery = client.get_device_battery(device=device_id)
            # CPU usage
            cpu_out = client.run_adb_command(
                "shell top -n 1 -b | head -5", device=device_id
            )
            # Memory
            mem_out = client.run_adb_command("shell cat /proc/meminfo", device=device_id)
            mem_total = 0
            mem_free = 0
            for line in mem_out.split('\n'):
                if 'MemTotal' in line:
                    mem_total = int(''.join(filter(str.isdigit, line))) // 1024
                elif 'MemAvailable' in line:
                    mem_free = int(''.join(filter(str.isdigit, line))) // 1024
            mem_used = mem_total - mem_free
            # Uptime
            uptime_out = client.run_adb_command("shell cat /proc/uptime", device=device_id)
            uptime_secs = float(uptime_out.split()[0]) if uptime_out else 0

            return jsonify({
                'battery_level': int(battery.get('level', 0)),
                'temperature': round(int(battery.get('temperature', 0)) / 10, 1),
                'cpu_raw': cpu_out[:200],
                'mem_total_mb': mem_total,
                'mem_used_mb': mem_used,
                'uptime_seconds': uptime_secs,
                'source': 'adb',
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/properties')
    def device_properties(device_id):
        try:
            def prop(key):
                return client.run_adb_command(f"shell getprop {key}", device=device_id)

            return jsonify({
                'os_version': prop('ro.build.version.release'),
                'sdk': prop('ro.build.version.sdk'),
                'kernel': prop('ro.build.display.id'),
                'hardware': prop('ro.hardware'),
                'model': prop('ro.product.model'),
                'manufacturer': prop('ro.product.manufacturer'),
                'resolution': client.run_adb_command("shell wm size", device=device_id),
                'density': client.run_adb_command("shell wm density", device=device_id),
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/files')
    def device_files(device_id):
        path = request.args.get('path', '/sdcard')
        # Try agent HTTP first
        agent_data = client.find_agent_device(device_id)
        if agent_data and agent_data.get('online'):
            try:
                agent_ip = agent_data.get('info', {}).get('ip') or request.remote_addr
                agent_port = agent_data.get('info', {}).get('agent_port', 9800)
                resp = requests.get(
                    f"http://{agent_ip}:{agent_port}/files/list",
                    params={"path": path}, timeout=5
                )
                if resp.ok:
                    data = resp.json()
                    # Normalize to match expected format
                    entries = []
                    for item in data.get('items', []):
                        entries.append({
                            'name': item.get('name'),
                            'is_dir': item.get('is_dir', False),
                            'size': item.get('size'),
                            'path': item.get('path'),
                        })
                    return jsonify({'path': path, 'entries': entries, 'source': 'agent'})
            except Exception as e:
                logger.debug(f"Agent file list failed, falling back to ADB: {e}")

        # Fallback: ADB
        try:
            output = client.run_adb_command(f"shell ls -la {path}", device=device_id)
            entries = []
            for line in output.split('\n'):
                parts = line.split()
                if len(parts) >= 8:
                    name = parts[-1]
                    is_dir = line.startswith('d')
                    size = parts[4] if not is_dir else None
                    entries.append({
                        'name': name,
                        'is_dir': is_dir,
                        'size': size,
                        'path': f"{path}/{name}",
                    })
            return jsonify({'path': path, 'entries': entries, 'source': 'adb'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/files/search')
    def device_files_search(device_id):
        """Proxy file search to agent."""
        agent_data = client.find_agent_device(device_id)
        if not agent_data or not agent_data.get('online'):
            return jsonify({'error': 'Agent not available for this device'}), 503
        try:
            agent_ip = agent_data.get('info', {}).get('ip') or request.remote_addr
            agent_port = agent_data.get('info', {}).get('agent_port', 9800)
            resp = requests.get(
                f"http://{agent_ip}:{agent_port}/files/search",
                params=request.args, timeout=30
            )
            return Response(resp.content, status=resp.status_code,
                            content_type=resp.headers.get('Content-Type', 'application/json'))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/files/upload', methods=['POST'])
    @limiter.limit("20 per minute")
    def device_files_upload(device_id):
        """Proxy file upload to agent."""
        agent_data = client.find_agent_device(device_id)
        if not agent_data or not agent_data.get('online'):
            return jsonify({'error': 'Agent not available for this device'}), 503
        try:
            agent_ip = agent_data.get('info', {}).get('ip') or request.remote_addr
            agent_port = agent_data.get('info', {}).get('agent_port', 9800)
            target_path = request.args.get('path', '')
            files = {}
            for key, f in request.files.items():
                files[key] = (f.filename, f.stream, f.content_type)
            resp = requests.post(
                f"http://{agent_ip}:{agent_port}/files/upload",
                params={"path": target_path},
                files=files, timeout=120
            )
            return Response(resp.content, status=resp.status_code,
                            content_type=resp.headers.get('Content-Type', 'application/json'))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/files/download')
    def device_files_download(device_id):
        """Proxy file download from agent."""
        agent_data = client.find_agent_device(device_id)
        if not agent_data or not agent_data.get('online'):
            return jsonify({'error': 'Agent not available for this device'}), 503
        try:
            agent_ip = agent_data.get('info', {}).get('ip') or request.remote_addr
            agent_port = agent_data.get('info', {}).get('agent_port', 9800)
            file_path = request.args.get('path', '')
            resp = requests.get(
                f"http://{agent_ip}:{agent_port}/files/read",
                params={"path": file_path}, timeout=60, stream=True
            )
            if not resp.ok:
                return Response(resp.content, status=resp.status_code,
                                content_type=resp.headers.get('Content-Type', 'application/json'))
            filename = file_path.split('/')[-1] if '/' in file_path else file_path
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': resp.headers.get('Content-Type', 'application/octet-stream'),
            }
            if 'Content-Length' in resp.headers:
                headers['Content-Length'] = resp.headers['Content-Length']
            return Response(resp.iter_content(chunk_size=8192), headers=headers)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return bp
