import base64
import logging
import time
import uuid
import threading
import queue
import json
import io
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)


class ApiAppMixin:
    # In-memory builds store for pipeline
    _builds = []
    _config = {}

    def api_app(self, host='0.0.0.0', port=5050, debug=True):
        try:
            self.start_uiautomator2_server()
        except Exception as e:
            logger.warning(f"UIAutomator2 init skipped: {e}")

        app = Flask(__name__)
        from config import CORS_ORIGINS
        CORS(app, origins=CORS_ORIGINS)
        client = self

        limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"],
                          storage_uri="memory://")

        @app.before_request
        def check_auth():
            # Skip auth for health, CORS preflight, SSE
            if request.path in ('/health',) or request.method == 'OPTIONS':
                return None
            # Agent device endpoints use agent token
            if request.path.startswith('/agent-device/'):
                token = request.headers.get('X-Agent-Token', '')
                if not client.validate_agent_token(token):
                    return jsonify({'error': 'Invalid agent token'}), 401
                return None
            # SSE endpoint: allow query param fallback (EventSource can't send headers)
            if request.path == '/events/stream':
                key = request.headers.get('X-API-Key') or request.args.get('api_key', '')
                if not client.validate_api_key(key):
                    return jsonify({'error': 'Invalid API key'}), 401
                return None
            # Stream endpoint: allow query param fallback (MJPEG streams can't send headers)
            if '/stream' in request.path and request.path.startswith('/devices/'):
                key = request.headers.get('X-API-Key') or request.args.get('api_key', '')
                if not client.validate_api_key(key):
                    return jsonify({'error': 'Invalid API key'}), 401
                return None
            # All other endpoints use API key
            key = request.headers.get('X-API-Key', '')
            if not client.validate_api_key(key):
                return jsonify({'error': 'Invalid API key'}), 401
            return None

        @app.after_request
        def add_security_headers(response):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            return response

        @app.after_request
        def audit_log(response):
            if request.method in ('POST', 'PUT', 'DELETE') and response.status_code < 500:
                client.log_activity(
                    action=f"{request.method} {request.path}",
                    details={'status': response.status_code},
                    source_ip=request.remote_addr,
                    authenticated=bool(request.headers.get('X-API-Key') or request.headers.get('X-Agent-Token')),
                )
            return response

        # -----------------------------------------------------------
        # SSE Broadcast Infrastructure
        # -----------------------------------------------------------
        _sse_clients = []
        _sse_lock = threading.Lock()

        def _sse_broadcast(event_type, data):
            """Push event to all connected SSE clients."""
            msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            with _sse_lock:
                dead = []
                for q in _sse_clients:
                    try:
                        q.put_nowait(msg)
                    except Exception:
                        dead.append(q)
                for q in dead:
                    _sse_clients.remove(q)

        def _sse_stream(client_queue):
            """Generator yielding SSE messages from a client's queue."""
            try:
                yield "event: connected\ndata: {}\n\n"
                while True:
                    try:
                        msg = client_queue.get(timeout=15)
                        yield msg
                    except queue.Empty:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                with _sse_lock:
                    if client_queue in _sse_clients:
                        _sse_clients.remove(client_queue)

        @app.route('/events/stream')
        def sse_stream():
            q = queue.Queue(maxsize=100)
            with _sse_lock:
                _sse_clients.append(q)
            return Response(
                _sse_stream(q),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
            )

        # -----------------------------------------------------------
        # Health
        # -----------------------------------------------------------
        @app.route('/health')
        def health():
            return jsonify({'status': 'ok', 'timestamp': time.time()})

        # -----------------------------------------------------------
        # Devices
        # -----------------------------------------------------------
        @app.route('/devices')
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

            # Merge agent-registered devices that aren't already in the ADB list
            now = time.time()
            for agent_id, agent_data in _agent_device_states.items():
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
                })

            return jsonify({'devices': connected, 'count': len(connected)})

        @app.route('/devices/<device_id>')
        def device_info(device_id):
            info = client.get_device_info(device_id)
            if info:
                return jsonify(info)
            return jsonify({'error': 'Device not found'}), 404

        @app.route('/devices/<device_id>/onboard', methods=['POST'])
        def device_onboard(device_id):
            """Manually trigger agent APK onboarding for a device."""
            try:
                result = client.ensure_agent_installed(device_id)
                client.log_activity('manual_onboard', device_id, result)
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/agent-apk/status')
        def agent_apk_status():
            """Check cached APK version and latest release info."""
            try:
                status = client.get_agent_apk_cache_status()
                return jsonify(status)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/proxy/device/<device_id>')
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

        # -----------------------------------------------------------
        # Dashboard
        # -----------------------------------------------------------
        @app.route('/dashboard/stats')
        def dashboard_stats():
            connected = client.get_devices()
            # Include agent-registered devices in fleet count
            now = time.time()
            adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
            agent_count = 0
            agent_busy = 0
            for agent_id, agent_data in _agent_device_states.items():
                if agent_id in adb_ids:
                    continue
                last_hb = agent_data.get('last_heartbeat', 0)
                if (now - last_hb) < 15:
                    agent_count += 1
                    state = agent_data.get('state', {})
                    if state.get('window', {}).get('package'):
                        agent_busy += 1

            total = len(connected) + agent_count
            busy = sum(1 for d in connected if d and d.get('currentPackageName')) + agent_busy
            utilization = round((busy / total * 100) if total > 0 else 0, 1)
            alerts = client.get_alerts(limit=100)
            critical = sum(1 for a in alerts if a['severity'] == 'critical')
            health = 'Healthy' if critical == 0 else 'Degraded'
            return jsonify({
                'fleet_count': total,
                'utilization': utilization,
                'avg_response_ms': 12,
                'health': health,
                'active_alerts': len(alerts),
            })

        # -----------------------------------------------------------
        # Device Control
        # -----------------------------------------------------------
        @app.route('/devices/<device_id>/adb', methods=['POST'])
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

        @app.route('/devices/<device_id>/reboot', methods=['POST'])
        @limiter.limit("5 per minute")
        def device_reboot(device_id):
            try:
                client.reboot_device(device=device_id)
                client.log_activity('reboot', device_id)
                return jsonify({'status': 'rebooting', 'device_id': device_id})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/devices/<device_id>/screenshot')
        def device_screenshot(device_id):
            try:
                data = client.take_screenshot(device_id)
                if data:
                    return Response(data, mimetype='image/png')
                return jsonify({'error': 'Screenshot failed'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/devices/<device_id>/tap', methods=['POST'])
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

        @app.route('/devices/<device_id>/press', methods=['POST'])
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

        @app.route('/devices/<device_id>/swipe', methods=['POST'])
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

        @app.route('/devices/<device_id>/battery')
        def device_battery(device_id):
            try:
                info = client.get_device_battery(device=device_id)
                return jsonify(info)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/devices/<device_id>/diagnostics')
        def device_diagnostics(device_id):
            """Return device diagnostics, preferring agent-sourced metrics when available."""
            try:
                # Check if we have recent agent-sourced metrics (< 10s old)
                agent_data = _find_agent_device(device_id)
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

        @app.route('/devices/<device_id>/properties')
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

        @app.route('/devices/<device_id>/files')
        def device_files(device_id):
            path = request.args.get('path', '/sdcard')
            # Try agent HTTP first
            agent_data = _find_agent_device(device_id)
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

        @app.route('/devices/<device_id>/files/search')
        def device_files_search(device_id):
            """Proxy file search to agent."""
            agent_data = _find_agent_device(device_id)
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

        @app.route('/devices/<device_id>/files/upload', methods=['POST'])
        @limiter.limit("20 per minute")
        def device_files_upload(device_id):
            """Proxy file upload to agent."""
            agent_data = _find_agent_device(device_id)
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

        @app.route('/devices/<device_id>/files/download')
        def device_files_download(device_id):
            """Proxy file download from agent."""
            agent_data = _find_agent_device(device_id)
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

        # -----------------------------------------------------------
        # Pipeline
        # -----------------------------------------------------------
        @app.route('/pipeline/builds')
        def pipeline_builds():
            return jsonify({
                'builds': sorted(client._builds, key=lambda b: b['created_at'], reverse=True)
            })

        @app.route('/pipeline/builds/<build_id>')
        def pipeline_build_detail(build_id):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if build:
                return jsonify(build)
            return jsonify({'error': 'Build not found'}), 404

        @app.route('/pipeline/builds', methods=['POST'])
        def pipeline_start_build():
            data = request.get_json(silent=True) or {}
            build_num = len(client._builds) + 1
            build = {
                'id': str(uuid.uuid4()),
                'number': build_num,
                'title': data.get('title', f'Build #{build_num}'),
                'status': 'created',
                'source': data.get('source', 'manual'),
                'ci_url': data.get('ci_url', ''),
                'created_at': time.time(),
                'started_at': None,
                'finished_at': None,
                'duration_ms': None,
                'total_tests': data.get('total_tests', 0),
                'passed': 0,
                'failed': 0,
                'errors': 0,
                'skipped': 0,
                'success_rate': 0,
                'tests': [],
                'failures': [],
            }
            client._builds.append(build)
            client.log_activity('build_started', details={'build_id': build['id']})
            _sse_broadcast('pipeline_build', build)
            return jsonify(build), 201

        @app.route('/pipeline/builds/<build_id>/status', methods=['PUT'])
        def pipeline_build_status(build_id):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if not build:
                return jsonify({'error': 'Build not found'}), 404
            data = request.get_json(silent=True) or {}
            new_status = data.get('status', '')
            if new_status not in ('running', 'completed', 'failed'):
                return jsonify({'error': 'Invalid status. Must be running, completed, or failed'}), 400

            build['status'] = new_status
            if new_status == 'running' and not build['started_at']:
                build['started_at'] = time.time()
            elif new_status in ('completed', 'failed'):
                build['finished_at'] = time.time()
                if build['started_at']:
                    build['duration_ms'] = int((build['finished_at'] - build['started_at']) * 1000)

                total = len(build['tests'])
                if total > 0:
                    build['success_rate'] = round(build['passed'] / total * 100, 1)

            _sse_broadcast('pipeline_build', build)
            return jsonify(build)

        @app.route('/pipeline/builds/<build_id>/tests', methods=['POST'])
        def pipeline_build_report_test(build_id):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if not build:
                return jsonify({'error': 'Build not found'}), 404
            data = request.get_json(silent=True) or {}

            test_record = {
                'id': data.get('id', str(uuid.uuid4())),
                'name': data.get('name', ''),
                'status': data.get('status', 'pass'),
                'duration': data.get('duration', 0),
                'device': data.get('device', ''),
                'error_message': data.get('error_message', ''),
                'traceback': data.get('traceback', ''),
                'screenshot_b64': data.get('screenshot_b64'),
                'reported_at': time.time(),
            }
            build['tests'].append(test_record)

            # Update counters
            status = test_record['status']
            if status == 'pass':
                build['passed'] += 1
            elif status == 'fail':
                build['failed'] += 1
                build['failures'].append({
                    'test_id': test_record['id'],
                    'test_name': test_record['name'],
                    'error': test_record['error_message'],
                    'trace': test_record['traceback'],
                })
            elif status == 'error':
                build['errors'] += 1
                build['failures'].append({
                    'test_id': test_record['id'],
                    'test_name': test_record['name'],
                    'error': test_record['error_message'],
                    'trace': test_record['traceback'],
                })
            elif status == 'skip':
                build['skipped'] += 1

            total = len(build['tests'])
            if total > 0:
                build['success_rate'] = round(build['passed'] / total * 100, 1)

            _sse_broadcast('pipeline_test', {
                'build_id': build_id,
                'test': test_record,
                'passed': build['passed'],
                'failed': build['failed'],
                'errors': build['errors'],
                'skipped': build['skipped'],
                'total': total,
                'success_rate': build['success_rate'],
            })
            return jsonify(test_record), 201

        @app.route('/pipeline/builds/<build_id>/tests/bulk', methods=['POST'])
        def pipeline_build_report_tests_bulk(build_id):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if not build:
                return jsonify({'error': 'Build not found'}), 404
            data = request.get_json(silent=True) or {}
            tests_data = data.get('tests', [])
            added = []

            for t in tests_data:
                test_record = {
                    'id': t.get('id', str(uuid.uuid4())),
                    'name': t.get('name', ''),
                    'status': t.get('status', 'pass'),
                    'duration': t.get('duration', 0),
                    'device': t.get('device', ''),
                    'error_message': t.get('error_message', ''),
                    'traceback': t.get('traceback', ''),
                    'screenshot_b64': t.get('screenshot_b64'),
                    'reported_at': time.time(),
                }
                build['tests'].append(test_record)
                added.append(test_record)

                status = test_record['status']
                if status == 'pass':
                    build['passed'] += 1
                elif status == 'fail':
                    build['failed'] += 1
                    build['failures'].append({
                        'test_id': test_record['id'],
                        'test_name': test_record['name'],
                        'error': test_record['error_message'],
                        'trace': test_record['traceback'],
                    })
                elif status == 'error':
                    build['errors'] += 1
                    build['failures'].append({
                        'test_id': test_record['id'],
                        'test_name': test_record['name'],
                        'error': test_record['error_message'],
                        'trace': test_record['traceback'],
                    })
                elif status == 'skip':
                    build['skipped'] += 1

            total = len(build['tests'])
            if total > 0:
                build['success_rate'] = round(build['passed'] / total * 100, 1)

            _sse_broadcast('pipeline_test', {
                'build_id': build_id,
                'bulk': True,
                'count': len(added),
                'passed': build['passed'],
                'failed': build['failed'],
                'errors': build['errors'],
                'skipped': build['skipped'],
                'total': total,
                'success_rate': build['success_rate'],
            })
            return jsonify({'tests': added, 'count': len(added)}), 201

        @app.route('/pipeline/builds/<build_id>/screenshots/<int:test_index>')
        def pipeline_build_screenshot(build_id, test_index):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if not build:
                return jsonify({'error': 'Build not found'}), 404
            tests_list = build.get('tests', [])
            if test_index < 0 or test_index >= len(tests_list):
                return jsonify({'error': 'Test index out of range'}), 404
            screenshot_b64 = tests_list[test_index].get('screenshot_b64')
            if not screenshot_b64:
                return jsonify({'error': 'No screenshot for this test'}), 404
            data = base64.b64decode(screenshot_b64)
            return Response(data, mimetype='image/png')

        @app.route('/pipeline/builds/<build_id>/failures')
        def pipeline_build_failures(build_id):
            build = next((b for b in client._builds if b['id'] == build_id), None)
            if not build:
                return jsonify({'error': 'Build not found'}), 404
            return jsonify({'failures': build.get('failures', [])})

        # -----------------------------------------------------------
        # Queue
        # -----------------------------------------------------------
        @app.route('/queue/status')
        def queue_status():
            return jsonify(client.get_all_queue_status())

        @app.route('/queue/<name>/send', methods=['POST'])
        def queue_send(name):
            data = request.get_json(silent=True) or {}
            body = data.get('body', data)
            msg_id = client.send_message(name, body)
            return jsonify({'message_id': msg_id})

        @app.route('/queue/<name>/receive', methods=['POST'])
        def queue_receive(name):
            msg = client.receive_message(name)
            if msg:
                return jsonify(msg)
            return jsonify({'message': None}), 204

        # -----------------------------------------------------------
        # Alerts
        # -----------------------------------------------------------
        @app.route('/alerts')
        def alerts_list():
            type_filter = request.args.get('type')
            limit = int(request.args.get('limit', 50))
            alerts = client.get_alerts(limit=limit, type_filter=type_filter)
            return jsonify({'alerts': alerts, 'count': len(alerts)})

        @app.route('/alerts', methods=['POST'])
        def alerts_create():
            data = request.get_json(silent=True) or {}
            alert = client.create_alert(
                device_id=data.get('device_id', 'unknown'),
                alert_type=data.get('type', 'error'),
                message=data.get('message', ''),
                severity=data.get('severity', 'warning'),
            )
            return jsonify(alert), 201

        @app.route('/alerts/<alert_id>/dismiss', methods=['PUT'])
        def alerts_dismiss(alert_id):
            if client.dismiss_alert(alert_id):
                return jsonify({'status': 'dismissed'})
            return jsonify({'error': 'Alert not found'}), 404

        # -----------------------------------------------------------
        # Activities
        # -----------------------------------------------------------
        @app.route('/activities')
        def activities_list():
            device_id = request.args.get('device_id')
            limit = int(request.args.get('limit', 50))
            activities = client.get_activities(limit=limit, device_id_filter=device_id)
            return jsonify({'activities': activities, 'count': len(activities)})

        # -----------------------------------------------------------
        # Config
        # -----------------------------------------------------------
        @app.route('/config')
        def config_get():
            return jsonify(client._config)

        @app.route('/config', methods=['PUT'])
        def config_update():
            data = request.get_json(silent=True) or {}
            client._config.update(data)
            return jsonify(client._config)

        # -----------------------------------------------------------
        # Automations
        # -----------------------------------------------------------
        @app.route('/automations/step-types')
        def automation_step_types():
            return jsonify(client.get_step_types())

        @app.route('/automations')
        def automations_list():
            automations = client.list_automations()
            return jsonify({'automations': automations, 'count': len(automations)})

        @app.route('/automations', methods=['POST'])
        def automations_create():
            data = request.get_json(silent=True) or {}
            name = data.get('name', '')
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            automation = client.create_automation(
                name=name,
                description=data.get('description', ''),
                steps=data.get('steps', []),
                tags=data.get('tags', []),
            )
            return jsonify(automation), 201

        @app.route('/automations/<automation_id>')
        def automations_get(automation_id):
            automation = client.get_automation(automation_id)
            if automation:
                return jsonify(automation)
            return jsonify({'error': 'Automation not found'}), 404

        @app.route('/automations/<automation_id>', methods=['PUT'])
        def automations_update(automation_id):
            data = request.get_json(silent=True) or {}
            result = client.update_automation(automation_id, data)
            if result is None:
                return jsonify({'error': 'Automation not found'}), 404
            updated = client.get_automation(automation_id)
            return jsonify(updated)

        @app.route('/automations/<automation_id>', methods=['DELETE'])
        def automations_delete(automation_id):
            if client.delete_automation(automation_id):
                return '', 204
            return jsonify({'error': 'Automation not found'}), 404

        @app.route('/automations/<automation_id>/run', methods=['POST'])
        def automations_run(automation_id):
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if not device_id:
                return jsonify({'error': 'device_id is required'}), 400
            self_heal = bool(data.get('self_heal', False))
            try:
                run_record = client.execute_automation(automation_id, device_id, self_heal=self_heal)
                return jsonify(run_record), 201
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/runs')
        def automation_runs_list():
            automation_id = request.args.get('automation_id')
            device_id = request.args.get('device_id')
            limit = int(request.args.get('limit', 50))
            runs = client.list_automation_runs(
                automation_id=automation_id,
                device_id=device_id,
                limit=limit,
            )
            return jsonify({'runs': runs, 'count': len(runs)})

        @app.route('/automations/runs/<run_id>')
        def automation_runs_get(run_id):
            run = client.get_automation_run(run_id)
            if run:
                return jsonify(run)
            return jsonify({'error': 'Run not found'}), 404

        @app.route('/automations/runs/<run_id>/cancel', methods=['POST'])
        def automation_runs_cancel(run_id):
            if client.cancel_automation_run(run_id):
                return jsonify({'status': 'cancelling'})
            return jsonify({'error': 'Run not found or already finished'}), 404

        # ── Recording ──
        @app.route('/automations/record/start', methods=['POST'])
        def automation_record_start():
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if not device_id:
                return jsonify({'error': 'device_id is required'}), 400
            try:
                session = client.start_recording(device_id)
                return jsonify(session), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/record/stop', methods=['POST'])
        def automation_record_stop():
            data = request.get_json(silent=True) or {}
            session_id = data.get('session_id')
            if not session_id:
                return jsonify({'error': 'session_id is required'}), 400
            try:
                steps = client.stop_recording(session_id)
                return jsonify({'steps': steps})
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/record/action', methods=['POST'])
        def automation_record_action():
            data = request.get_json(silent=True) or {}
            session_id = data.get('session_id')
            action = data.get('action')
            if not session_id or not action:
                return jsonify({'error': 'session_id and action are required'}), 400
            try:
                count = client.record_action(session_id, action)
                return jsonify({'count': count})
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # ── Schedules ──
        @app.route('/automations/schedules')
        def automation_schedules_list():
            automation_id = request.args.get('automation_id')
            schedules = client.list_schedules(automation_id=automation_id)
            return jsonify({'schedules': schedules, 'count': len(schedules)})

        @app.route('/automations/schedules', methods=['POST'])
        def automation_schedules_create():
            data = request.get_json(silent=True) or {}
            automation_id = data.get('automation_id')
            device_id = data.get('device_id')
            interval_minutes = data.get('interval_minutes')
            if not automation_id or not device_id or not interval_minutes:
                return jsonify({'error': 'automation_id, device_id and interval_minutes are required'}), 400
            try:
                schedule = client.create_schedule(
                    automation_id=automation_id,
                    device_id=device_id,
                    interval_minutes=int(interval_minutes),
                    enabled=data.get('enabled', True),
                )
                return jsonify(schedule), 201
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/schedules/<schedule_id>', methods=['PUT'])
        def automation_schedules_update(schedule_id):
            data = request.get_json(silent=True) or {}
            result = client.update_schedule(schedule_id, data)
            if result is None:
                return jsonify({'error': 'Schedule not found'}), 404
            return jsonify(result)

        @app.route('/automations/schedules/<schedule_id>', methods=['DELETE'])
        def automation_schedules_delete(schedule_id):
            if client.delete_schedule(schedule_id):
                return '', 204
            return jsonify({'error': 'Schedule not found'}), 404

        # ── Failure Screenshots ──
        @app.route('/automations/runs/<run_id>/screenshots/<int:step_index>')
        def automation_run_screenshot(run_id, step_index):
            run = client.get_automation_run(run_id)
            if not run:
                return jsonify({'error': 'Run not found'}), 404
            step_results = run.get('step_results', [])
            if step_index < 0 or step_index >= len(step_results):
                return jsonify({'error': 'Step index out of range'}), 404
            screenshot_b64 = step_results[step_index].get('failure_screenshot')
            if not screenshot_b64:
                return jsonify({'error': 'No failure screenshot for this step'}), 404
            import base64
            data = base64.b64decode(screenshot_b64)
            return Response(data, mimetype='image/png')

        # ── Clone / Export / Import ──
        @app.route('/automations/<automation_id>/clone', methods=['POST'])
        def automations_clone(automation_id):
            data = request.get_json(silent=True) or {}
            try:
                cloned = client.clone_automation(automation_id, new_name=data.get('name'))
                return jsonify(cloned), 201
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/<automation_id>/export')
        def automations_export(automation_id):
            try:
                exported = client.export_automation(automation_id)
                return jsonify(exported)
            except ValueError as e:
                return jsonify({'error': str(e)}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/import', methods=['POST'])
        def automations_import():
            data = request.get_json(silent=True) or {}
            if not data.get('name'):
                return jsonify({'error': 'name is required'}), 400
            try:
                automation = client.import_automation(data)
                return jsonify(automation), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # ── NL Automation (AI-powered) ──
        @app.route('/automations/generate', methods=['POST'])
        def automations_generate():
            data = request.get_json(silent=True) or {}
            description = data.get('description', '')
            if not description:
                return jsonify({'error': 'description is required'}), 400
            device_id = data.get('device_id')
            try:
                result = client.generate_automation_steps(description, device_id=device_id)
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/refine-step', methods=['POST'])
        def automations_refine_step():
            data = request.get_json(silent=True) or {}
            step = data.get('step')
            instruction = data.get('instruction', '')
            if not step or not instruction:
                return jsonify({'error': 'step and instruction are required'}), 400
            device_id = data.get('device_id')
            try:
                refined = client.refine_step(step, instruction, device_id=device_id)
                return jsonify(refined)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/automations/<automation_id>/explain')
        def automations_explain(automation_id):
            try:
                result = client.explain_automation(automation_id)
                if 'error' in result and result['error'] == 'Automation not found':
                    return jsonify(result), 404
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/devices/<device_id>/ui-hierarchy')
        def device_ui_hierarchy(device_id):
            try:
                hierarchy = client.fetch_ui_hierarchy(device_id)
                if hierarchy:
                    return jsonify(hierarchy)
                return jsonify({'error': 'Could not fetch UI hierarchy'}), 500
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # -----------------------------------------------------------
        # Profiles
        # -----------------------------------------------------------
        @app.route('/profiles')
        def profiles_list():
            profiles = client.list_profiles()
            return jsonify({'profiles': profiles, 'count': len(profiles)})

        @app.route('/profiles', methods=['POST'])
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

        @app.route('/profiles/<profile_id>')
        def profiles_get(profile_id):
            profile = client.get_profile(profile_id)
            if profile:
                return jsonify(profile)
            return jsonify({'error': 'Profile not found'}), 404

        @app.route('/profiles/device/<device_id>')
        def profiles_by_device(device_id):
            profile = client.get_profile_by_device(device_id)
            if profile:
                return jsonify(profile)
            return jsonify({'error': 'No profile for this device'}), 404

        @app.route('/profiles/<profile_id>', methods=['PUT'])
        def profiles_update(profile_id):
            data = request.get_json(silent=True) or {}
            result = client.update_profile(profile_id, data)
            if result is None:
                return jsonify({'error': 'Profile not found'}), 404
            return jsonify(result)

        @app.route('/profiles/<profile_id>', methods=['DELETE'])
        def profiles_delete(profile_id):
            if client.delete_profile(profile_id):
                return '', 204
            return jsonify({'error': 'Profile not found'}), 404

        # -----------------------------------------------------------
        # Fleet Management
        # -----------------------------------------------------------
        @app.route('/fleet/groups')
        def fleet_groups_list():
            groups = client.list_device_groups()
            return jsonify({'groups': groups, 'count': len(groups)})

        @app.route('/fleet/groups', methods=['POST'])
        def fleet_groups_create():
            data = request.get_json(silent=True) or {}
            name = data.get('name', '')
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            group = client.create_device_group(
                name=name,
                description=data.get('description', ''),
                color=data.get('color', '#10b981'),
                tags=data.get('tags', []),
                device_ids=data.get('device_ids', []),
            )
            return jsonify(group), 201

        @app.route('/fleet/groups/<group_id>')
        def fleet_groups_get(group_id):
            group = client.get_device_group(group_id)
            if group:
                return jsonify(group)
            return jsonify({'error': 'Group not found'}), 404

        @app.route('/fleet/groups/<group_id>', methods=['PUT'])
        def fleet_groups_update(group_id):
            data = request.get_json(silent=True) or {}
            result = client.update_device_group(group_id, data)
            if result is None:
                return jsonify({'error': 'Group not found'}), 404
            return jsonify(result)

        @app.route('/fleet/groups/<group_id>', methods=['DELETE'])
        def fleet_groups_delete(group_id):
            if client.delete_device_group(group_id):
                return '', 204
            return jsonify({'error': 'Group not found'}), 404

        @app.route('/fleet/groups/<group_id>/devices', methods=['POST'])
        def fleet_group_add_device(group_id):
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id', '')
            if not device_id:
                return jsonify({'error': 'device_id is required'}), 400
            result = client.add_device_to_group(group_id, device_id)
            if result is None:
                return jsonify({'error': 'Group not found'}), 404
            return jsonify(result)

        @app.route('/fleet/groups/<group_id>/devices/<device_id>', methods=['DELETE'])
        def fleet_group_remove_device(group_id, device_id):
            result = client.remove_device_from_group(group_id, device_id)
            if result is None:
                return jsonify({'error': 'Group not found'}), 404
            return jsonify(result)

        # ── Bulk Actions ──
        @app.route('/fleet/groups/<group_id>/bulk/command', methods=['POST'])
        @limiter.limit("10 per minute")
        def fleet_bulk_command(group_id):
            group = client.get_device_group(group_id)
            if not group:
                return jsonify({'error': 'Group not found'}), 404
            data = request.get_json(silent=True) or {}
            command = data.get('command', '')
            if not command:
                return jsonify({'error': 'command is required'}), 400
            results = []
            for did in group['device_ids']:
                try:
                    output = client.run_adb_command(f"shell {command}", device=did)
                    results.append({'device_id': did, 'status': 'ok', 'output': output})
                except Exception as e:
                    results.append({'device_id': did, 'status': 'error', 'error': str(e)})
            client.log_activity('bulk_command', details={
                'group_id': group_id, 'command': command, 'device_count': len(group['device_ids']),
            })
            _sse_broadcast('bulk_action_complete', {
                'group_id': group_id, 'action': 'command', 'results': results,
            })
            return jsonify({'results': results})

        @app.route('/fleet/groups/<group_id>/bulk/install', methods=['POST'])
        @limiter.limit("10 per minute")
        def fleet_bulk_install(group_id):
            group = client.get_device_group(group_id)
            if not group:
                return jsonify({'error': 'Group not found'}), 404
            results = []
            for did in group['device_ids']:
                try:
                    result = client.ensure_agent_installed(did)
                    results.append({'device_id': did, 'status': 'ok', 'detail': result})
                except Exception as e:
                    results.append({'device_id': did, 'status': 'error', 'error': str(e)})
            client.log_activity('bulk_install', details={
                'group_id': group_id, 'device_count': len(group['device_ids']),
            })
            _sse_broadcast('bulk_action_complete', {
                'group_id': group_id, 'action': 'install', 'results': results,
            })
            return jsonify({'results': results})

        @app.route('/fleet/groups/<group_id>/bulk/reboot', methods=['POST'])
        @limiter.limit("10 per minute")
        def fleet_bulk_reboot(group_id):
            group = client.get_device_group(group_id)
            if not group:
                return jsonify({'error': 'Group not found'}), 404
            results = []
            for did in group['device_ids']:
                try:
                    client.reboot_device(device=did)
                    results.append({'device_id': did, 'status': 'ok'})
                except Exception as e:
                    results.append({'device_id': did, 'status': 'error', 'error': str(e)})
            client.log_activity('bulk_reboot', details={
                'group_id': group_id, 'device_count': len(group['device_ids']),
            })
            _sse_broadcast('bulk_action_complete', {
                'group_id': group_id, 'action': 'reboot', 'results': results,
            })
            return jsonify({'results': results})

        # ── Per-Device Tags ──
        @app.route('/devices/<device_id>/tags')
        def device_tags_get(device_id):
            tags = client.get_device_tags(device_id)
            groups = client.get_groups_for_device(device_id)
            return jsonify({'device_id': device_id, 'tags': tags, 'groups': groups})

        @app.route('/devices/<device_id>/tags', methods=['PUT'])
        def device_tags_update(device_id):
            data = request.get_json(silent=True) or {}
            tags = data.get('tags', [])
            result = client.set_device_tags(device_id, tags)
            return jsonify({'device_id': device_id, 'tags': result})

        # ── Device Locking ──
        @app.route('/devices/<device_id>/lock', methods=['POST'])
        def device_lock(device_id):
            data = request.get_json(silent=True) or {}
            owner = data.get('owner', '')
            if not owner:
                return jsonify({'error': 'owner is required'}), 400
            timeout = data.get('timeout')
            lock_info = client.acquire_device_lock(device_id, owner, timeout=timeout)
            if lock_info is None:
                existing = client.get_device_lock_status(device_id)
                return jsonify({'error': 'Device is already locked', 'lock': existing}), 409
            return jsonify(lock_info)

        @app.route('/devices/<device_id>/unlock', methods=['POST'])
        def device_unlock(device_id):
            data = request.get_json(silent=True) or {}
            owner = data.get('owner')
            lock_id = data.get('lock_id')
            if not owner and not lock_id:
                return jsonify({'error': 'owner or lock_id is required'}), 400
            released = client.release_device_lock(device_id, owner=owner, lock_id=lock_id)
            if not released:
                return jsonify({'error': 'Lock not found or owner mismatch'}), 404
            return jsonify({'status': 'unlocked', 'device_id': device_id})

        @app.route('/devices/available')
        def devices_available():
            available = client.get_available_devices()
            return jsonify({'devices': available, 'count': len(available)})

        # ── Fleet Health ──
        @app.route('/fleet/health')
        def fleet_health():
            connected = client.get_devices()
            now = time.time()
            adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
            for agent_id, agent_data in _agent_device_states.items():
                if agent_id in adb_ids:
                    continue
                info = agent_data.get('info', {})
                state = agent_data.get('state', {})
                metrics = state.get('metrics', {})
                last_hb = agent_data.get('last_heartbeat', 0)
                online = (now - last_hb) < 15 if last_hb else False
                connected.append({
                    'device_id': agent_id,
                    'online': online,
                    'cpu_percent': metrics.get('cpu_percent'),
                    'battery_level': metrics.get('battery_level'),
                    'ram_used_mb': metrics.get('ram_used_mb'),
                    'ram_total_mb': metrics.get('ram_total_mb'),
                    'temperature': metrics.get('battery_temperature'),
                })

            total = len(connected)
            online_count = sum(1 for d in connected if d.get('online', True))
            offline_count = total - online_count

            cpus = [d['cpu_percent'] for d in connected if d.get('cpu_percent') is not None]
            batteries = [d['battery_level'] for d in connected if d.get('battery_level') is not None]
            rams_used = [d.get('ram_used_mb', 0) for d in connected if d.get('ram_used_mb') is not None]
            rams_total = [d.get('ram_total_mb', 0) for d in connected if d.get('ram_total_mb') is not None]
            temps = [d.get('temperature', 0) for d in connected if d.get('temperature') is not None and d.get('temperature') > 0]

            avg_cpu = round(sum(cpus) / len(cpus), 1) if cpus else 0
            avg_battery = round(sum(batteries) / len(batteries), 1) if batteries else 0
            avg_temp = round(sum(temps) / len(temps), 1) if temps else 0

            # Health classification
            healthy = 0
            warning = 0
            critical = 0
            for d in connected:
                cpu = d.get('cpu_percent', 0) or 0
                bat = d.get('battery_level', 100) or 100
                tmp = d.get('temperature', 0) or 0
                if cpu > 90 or bat < 10 or tmp > 50:
                    critical += 1
                elif cpu > 70 or bat < 20 or tmp > 45:
                    warning += 1
                else:
                    healthy += 1

            device_summaries = [{
                'device_id': d.get('device_id', d.get('serial', '')),
                'cpu_percent': d.get('cpu_percent'),
                'battery_level': d.get('battery_level'),
                'ram_used_mb': d.get('ram_used_mb'),
                'ram_total_mb': d.get('ram_total_mb'),
                'temperature': d.get('temperature'),
                'online': d.get('online', True),
            } for d in connected]

            return jsonify({
                'total_devices': total,
                'online_devices': online_count,
                'offline_devices': offline_count,
                'avg_cpu': avg_cpu,
                'avg_battery': avg_battery,
                'total_ram_used_mb': sum(rams_used),
                'total_ram_total_mb': sum(rams_total),
                'avg_temperature': avg_temp,
                'health_distribution': {
                    'healthy': healthy,
                    'warning': warning,
                    'critical': critical,
                },
                'devices': device_summaries,
            })

        @app.route('/fleet/compare')
        def fleet_compare():
            device_ids = request.args.get('devices', '')
            ids = [d.strip() for d in device_ids.split(',') if d.strip()][:4]
            results = []
            for did in ids:
                agent_data = _find_agent_device(did)
                if agent_data:
                    state = agent_data.get('state', {})
                    metrics = state.get('metrics', {})
                    last_hb = agent_data.get('last_heartbeat', 0)
                    now = time.time()
                    results.append({
                        'device_id': did,
                        'online': (now - last_hb) < 15 if last_hb else False,
                        'model': agent_data.get('info', {}).get('model', 'Unknown'),
                        'cpu_percent': metrics.get('cpu_percent', 0),
                        'battery_level': metrics.get('battery_level', 0),
                        'ram_used_mb': metrics.get('ram_used_mb', 0),
                        'ram_total_mb': metrics.get('ram_total_mb', 0),
                        'temperature': metrics.get('battery_temperature', 0),
                        'is_charging': metrics.get('is_charging', False),
                    })
                else:
                    try:
                        battery = client.get_device_battery(device=did)
                        results.append({
                            'device_id': did,
                            'online': True,
                            'model': client.run_adb_command("shell getprop ro.product.model", device=did).strip(),
                            'cpu_percent': 0,
                            'battery_level': int(battery.get('level', 0)),
                            'ram_used_mb': 0,
                            'ram_total_mb': 0,
                            'temperature': round(int(battery.get('temperature', 0)) / 10, 1),
                            'is_charging': False,
                        })
                    except Exception:
                        results.append({
                            'device_id': did,
                            'online': False,
                            'model': 'Unknown',
                            'cpu_percent': 0,
                            'battery_level': 0,
                            'ram_used_mb': 0,
                            'ram_total_mb': 0,
                            'temperature': 0,
                            'is_charging': False,
                        })
            return jsonify({'devices': results})

        # -----------------------------------------------------------
        # AI Agent
        # -----------------------------------------------------------
        @app.route('/agent/status')
        def agent_status_all():
            return jsonify(client.get_all_agent_status())

        @app.route('/agent/<device_id>/status')
        def agent_status(device_id):
            return jsonify(client.get_agent_status(device_id))

        @app.route('/agent/<device_id>/start', methods=['POST'])
        def agent_start(device_id):
            profile = client.get_profile_by_device(device_id)
            if not profile:
                return jsonify({'error': 'No profile found for this device. Create a profile first.'}), 400
            model_name = profile.get('model_name', '') or None
            result = client.start_agent(device_id, profile, model_name=model_name)
            if 'error' in result:
                return jsonify(result), 409
            client.log_activity('agent_start', device_id)
            return jsonify(result)

        @app.route('/agent/<device_id>/stop', methods=['POST'])
        def agent_stop(device_id):
            result = client.stop_agent(device_id)
            client.log_activity('agent_stop', device_id)
            return jsonify(result)

        @app.route('/agent/<device_id>/command', methods=['POST'])
        def agent_command(device_id):
            data = request.get_json(silent=True) or {}
            command = data.get('command', '')
            if not command:
                return jsonify({'error': 'command is required'}), 400
            priority = data.get('priority', 'normal')
            cmd = client.enqueue_command(device_id, command, priority)
            client.log_activity('agent_command', device_id, {'command': command, 'priority': priority})
            return jsonify(cmd), 201

        @app.route('/agent/<device_id>/commands')
        def agent_commands(device_id):
            return jsonify({'commands': client.get_command_queue(device_id)})

        @app.route('/agent/<device_id>/logs')
        def agent_logs(device_id):
            limit = int(request.args.get('limit', 50))
            return jsonify({'logs': client.get_agent_logs(device_id, limit)})

        @app.route('/devices/<device_id>/conversation/history')
        def conversation_history(device_id):
            messages = client.get_conversation_history(device_id)
            return jsonify({'messages': messages, 'turn_count': len(messages)})

        @app.route('/devices/<device_id>/conversation', methods=['DELETE'])
        def conversation_clear(device_id):
            result = client.clear_conversation(device_id)
            return jsonify(result)

        @app.route('/devices/<device_id>/agent/usage')
        def agent_usage(device_id):
            usage = client.get_agent_usage(device_id)
            return jsonify(usage)

        @app.route('/devices/<device_id>/agent/model', methods=['PATCH'])
        def agent_model_switch(device_id):
            data = request.get_json(silent=True) or {}
            model_name = data.get('model_name', '')
            if not model_name:
                return jsonify({'error': 'model_name is required'}), 400
            result = client.switch_agent_model(device_id, model_name)
            return jsonify(result)

        # -----------------------------------------------------------
        # Agent Device (on-device DeviceKitAgent APK endpoints)
        # -----------------------------------------------------------
        # In-memory cache for agent device state (backed by AgentDevice rows so the
        # registry survives a restart). The event ring buffer stays ephemeral.
        _agent_device_states = {}
        _agent_device_events = []
        _agent_device_serial_index = {}  # serial -> device_id mapping

        # Hydrate the cache from persisted rows at boot.
        try:
            for _row in client.load_agent_devices():
                _did = _row['device_id']
                _serial = _row.pop('serial', None)
                _agent_device_states[_did] = {
                    'device_id': _did,
                    'info': _row.get('info', {}),
                    'registered_at': _row.get('registered_at'),
                    'last_heartbeat': _row.get('last_heartbeat'),
                    'state': _row.get('state', {}),
                    'online': _row.get('online', False),
                }
                if _serial:
                    _agent_device_serial_index[_serial] = _did
            if _agent_device_states:
                logger.info(f"Loaded {len(_agent_device_states)} persisted agent device(s)")
        except Exception as e:
            logger.warning(f"Could not load persisted agent devices: {e}")

        @app.route('/agent-device/register', methods=['POST'])
        def agent_device_register():
            data = request.get_json(silent=True) or {}
            model = data.get('model', 'unknown')
            manufacturer = data.get('manufacturer', 'unknown')
            device_id = f"{manufacturer}_{model}".replace(' ', '_')
            now = time.time()
            _agent_device_states[device_id] = {
                'device_id': device_id,
                'info': data,
                'registered_at': now,
                'last_heartbeat': now,
                'state': {},
                'online': True,
            }
            # Index by serial number for ADB cross-reference
            serial = data.get('serial')
            if serial:
                _agent_device_serial_index[serial] = device_id
            client.save_agent_device(
                device_id, info=data, serial=serial, registered_at=now,
                last_heartbeat=now, state={}, online=True,
            )
            logger.info(f"Agent device registered: {device_id} (serial={serial})")
            client.log_activity('agent_device_register', device_id, data)
            _sse_broadcast('device_connected', {'device_id': device_id, 'info': data})
            _sse_broadcast('device_new', {'device_id': device_id, 'info': data})
            return jsonify({'device_id': device_id, 'status': 'registered'})

        @app.route('/agent-device/state', methods=['POST'])
        def agent_device_state():
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if device_id and device_id in _agent_device_states:
                now = time.time()
                _agent_device_states[device_id]['state'] = data
                _agent_device_states[device_id]['last_heartbeat'] = now
                client.update_agent_device_fields(
                    device_id, state=data, last_heartbeat=now, online=True,
                )
                _sse_broadcast('device_state', {'device_id': device_id, 'state': data})

                # Auto-generate alerts from agent metrics
                metrics = data.get('metrics', {})
                if metrics:
                    battery = metrics.get('battery_level', 100)
                    temp = metrics.get('battery_temperature', 0)

                    # Low battery alert (<20%)
                    if battery < 20:
                        recent = [a for a in client._alerts
                                  if a['device_id'] == device_id and a['type'] == 'low_battery'
                                  and a['status'] == 'active' and time.time() - a['created_at'] < 300]
                        if not recent:
                            alert = client.create_alert(
                                device_id, 'low_battery',
                                f'Battery at {battery}%',
                                severity='critical' if battery < 10 else 'warning'
                            )
                            _sse_broadcast('alert', alert)

                    # Overheating alert (>45C)
                    if temp > 45:
                        recent = [a for a in client._alerts
                                  if a['device_id'] == device_id and a['type'] == 'overheating'
                                  and a['status'] == 'active' and time.time() - a['created_at'] < 300]
                        if not recent:
                            alert = client.create_alert(
                                device_id, 'overheating',
                                f'Temperature at {temp}C',
                                severity='critical' if temp > 50 else 'warning'
                            )
                            _sse_broadcast('alert', alert)

                    # Storage full alert (free < 5% of total)
                    storage = data.get('storage', metrics.get('storage', {}))
                    if storage:
                        total = storage.get('total', 0)
                        free = storage.get('free', total)
                        if total > 0 and free < total * 0.05:
                            recent = [a for a in client._alerts
                                      if a['device_id'] == device_id and a['type'] == 'storage_full'
                                      and a['status'] == 'active' and time.time() - a['created_at'] < 300]
                            if not recent:
                                pct = round(free / total * 100, 1)
                                alert = client.create_alert(
                                    device_id, 'storage_full',
                                    f'Storage {pct}% free ({free} MB remaining)',
                                    severity='critical' if free < total * 0.02 else 'warning'
                                )
                                _sse_broadcast('alert', alert)

            return jsonify({'status': 'ok'})

        @app.route('/agent-device/heartbeat', methods=['POST'])
        def agent_device_heartbeat():
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if device_id and device_id in _agent_device_states:
                now = time.time()
                _agent_device_states[device_id]['last_heartbeat'] = now
                _agent_device_states[device_id]['online'] = True
                client.update_agent_device_fields(device_id, last_heartbeat=now, online=True)
                _sse_broadcast('device_heartbeat', {'device_id': device_id, 'timestamp': now})
            return jsonify({'status': 'ok'})

        @app.route('/agent-device/event', methods=['POST'])
        def agent_device_event():
            data = request.get_json(silent=True) or {}
            _agent_device_events.append(data)
            # Keep last 500 events
            if len(_agent_device_events) > 500:
                _agent_device_events.pop(0)
            device_id = data.get('device_id', 'unknown')
            event_type = data.get('event', 'unknown')
            logger.info(f"Agent device event: {device_id} -> {event_type}")
            _sse_broadcast('device_event', data)
            return jsonify({'status': 'ok'})

        @app.route('/agent-device/<device_id>/commands')
        def agent_device_commands(device_id):
            # Placeholder for command queue from server to on-device agent
            return jsonify({'commands': []})

        @app.route('/agent-device/<device_id>/metrics')
        def agent_device_metrics(device_id):
            """Return raw agent-sourced metrics for a device."""
            agent_data = _find_agent_device(device_id)
            if not agent_data:
                return jsonify({'error': 'Agent device not found'}), 404

            state = agent_data.get('state', {})
            metrics = state.get('metrics', {})
            if not metrics:
                return jsonify({'error': 'No metrics available'}), 404

            last_hb = agent_data.get('last_heartbeat', 0)
            network = metrics.get('network', {})
            return jsonify({
                'device_id': device_id,
                'metrics': {
                    'cpu_percent': metrics.get('cpu_percent', 0),
                    'ram_used_mb': metrics.get('ram_used_mb', 0),
                    'ram_total_mb': metrics.get('ram_total_mb', 0),
                    'battery_level': metrics.get('battery_level', 0),
                    'battery_temperature': metrics.get('battery_temperature', 0),
                    'is_charging': metrics.get('is_charging', False),
                    'network': {
                        'type': network.get('type', 'unknown'),
                        'rx_rate': network.get('rx_rate', 0),
                        'tx_rate': network.get('tx_rate', 0),
                    },
                },
                'last_heartbeat': last_hb,
                'online': agent_data.get('online', False),
                'age_seconds': round(time.time() - last_hb, 1) if last_hb else None,
                'source': 'agent',
            })

        @app.route('/agent-device/status')
        def agent_device_status():
            # Mark stale devices as offline (no heartbeat in 15s)
            now = time.time()
            for d in _agent_device_states.values():
                if now - (d.get('last_heartbeat') or 0) > 15:
                    if d.get('online', False):
                        d['online'] = False
                        client.update_agent_device_fields(d.get('device_id'), online=False)
                        _sse_broadcast('device_disconnected', {'device_id': d.get('device_id')})
            return jsonify({'devices': list(_agent_device_states.values())})

        @app.route('/agent-device/events')
        def agent_device_events():
            limit = int(request.args.get('limit', 50))
            return jsonify({'events': _agent_device_events[-limit:]})

        def _find_agent_device(device_id):
            """Find agent device state by device_id or serial number cross-reference."""
            # Direct lookup
            if device_id in _agent_device_states:
                return _agent_device_states[device_id]
            # Try serial number index (ADB device IDs may be serial numbers)
            if device_id in _agent_device_serial_index:
                mapped_id = _agent_device_serial_index[device_id]
                return _agent_device_states.get(mapped_id)
            # Fuzzy match: check if device_id is a substring of any agent device ID
            for agent_id, state in _agent_device_states.items():
                if device_id in agent_id or agent_id in device_id:
                    return state
                # Check serial in info
                info = state.get('info', {})
                if info.get('serial') == device_id:
                    return state
            return None

        # -----------------------------------------------------------
        # Real-Time Device Streaming
        # -----------------------------------------------------------

        def _find_agent_device_for_stream(device_id):
            """Wrapper so StreamingMixin can locate agent device data."""
            return _find_agent_device(device_id)

        # Attach to client so StreamingMixin can call it
        client._find_agent_device_for_stream = _find_agent_device_for_stream

        @app.route('/devices/<device_id>/stream')
        def device_stream(device_id):
            fps = request.args.get('fps', 10, type=int)
            quality = request.args.get('quality', 50, type=int)
            result = client.proxy_device_stream(device_id, fps=fps, quality=quality)
            if result is None:
                return jsonify({'error': 'Stream not available for this device'}), 503
            generator, content_type = result
            _sse_broadcast('stream_viewer', {
                'device_id': device_id,
                'viewers': client.get_stream_viewers(device_id) + 1,
            })

            def on_close_generator():
                try:
                    yield from generator
                finally:
                    _sse_broadcast('stream_viewer', {
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

        @app.route('/devices/<device_id>/stream/status')
        def device_stream_status(device_id):
            viewers = client.get_stream_viewers(device_id)
            available = client.is_stream_available(device_id)
            return jsonify({'viewers': viewers, 'available': available})

        @app.route('/devices/<device_id>/sessions/record', methods=['POST'])
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

        @app.route('/devices/<device_id>/sessions/<session_id>/stop', methods=['POST'])
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

        @app.route('/devices/<device_id>/sessions')
        def device_stream_sessions(device_id):
            sessions = client.get_recording_sessions(device_id)
            return jsonify({'sessions': sessions, 'count': len(sessions)})

        @app.route('/devices/<device_id>/sessions/<session_id>')
        def device_stream_session_detail(device_id, session_id):
            meta = client.get_recording_metadata(session_id)
            if meta is None:
                return jsonify({'error': 'Recording session not found'}), 404
            return jsonify(meta)

        @app.route('/devices/<device_id>/sessions/<session_id>/frames/<int:frame_index>')
        def device_stream_session_frame(device_id, session_id, frame_index):
            data = client.get_recording_frame(session_id, frame_index)
            if data is None:
                return jsonify({'error': 'Frame not found'}), 404
            return Response(data, mimetype='image/jpeg')

        @app.route('/devices/<device_id>/sessions/<session_id>/events', methods=['POST'])
        def device_stream_session_event(device_id, session_id):
            data = request.get_json(silent=True) or {}
            count = client.record_stream_event(session_id, data)
            if count is None:
                return jsonify({'error': 'Session not found or not active'}), 404
            return jsonify({'count': count})

        # -----------------------------------------------------------
        # Visual Regression Testing
        # -----------------------------------------------------------

        @app.route('/automations/<automation_id>/baselines', methods=['GET'])
        def list_baselines(automation_id):
            baselines = client.list_baselines(automation_id)
            return jsonify({'baselines': baselines, 'count': len(baselines)})

        @app.route('/automations/<automation_id>/baselines', methods=['POST'])
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

        @app.route('/automations/<automation_id>/baselines/<baseline_id>')
        def get_baseline_detail(automation_id, baseline_id):
            baseline = client.get_baseline(baseline_id)
            if not baseline or baseline.get('automation_id') != automation_id:
                return jsonify({'error': 'Baseline not found'}), 404
            return jsonify({k: v for k, v in baseline.items() if k != 'image_b64'})

        @app.route('/automations/<automation_id>/baselines/<baseline_id>/image')
        def get_baseline_image(automation_id, baseline_id):
            image_data = client.get_baseline_image(baseline_id)
            if image_data is None:
                return jsonify({'error': 'Baseline not found'}), 404
            return Response(image_data, mimetype='image/jpeg')

        @app.route('/automations/<automation_id>/baselines/<baseline_id>', methods=['PUT'])
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

        @app.route('/automations/<automation_id>/baselines/<baseline_id>', methods=['DELETE'])
        def delete_baseline(automation_id, baseline_id):
            if client.delete_baseline(baseline_id):
                return '', 204
            return jsonify({'error': 'Baseline not found'}), 404

        @app.route('/automations/<automation_id>/baselines/<baseline_id>/compare', methods=['POST'])
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

        @app.route('/automations/runs/<run_id>/regression-report')
        def regression_report(run_id):
            report = client.generate_regression_report(run_id)
            if report is None:
                return jsonify({'error': 'Run not found'}), 404
            return jsonify(report)

        # -----------------------------------------------------------
        # Fleet Query Language
        # -----------------------------------------------------------

        def _get_all_devices():
            """Helper to get merged ADB + agent device list for queries."""
            connected = client.get_devices()
            adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
            now = time.time()
            for agent_id, agent_data in _agent_device_states.items():
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
                })
            return connected

        @app.route('/fleet/query')
        def fleet_query():
            """Execute a fleet query expression against all devices."""
            expression = request.args.get('q', '').strip()
            fmt = request.args.get('format', 'json').lower()
            if not expression:
                return jsonify({'error': 'Query parameter "q" is required'}), 400
            try:
                devices = _get_all_devices()
                matches = client.execute_fleet_query(expression, devices=devices)
                if fmt == 'csv':
                    csv_data = client.export_query_csv(matches)
                    return csv_data, 200, {
                        'Content-Type': 'text/csv',
                        'Content-Disposition': 'attachment; filename=fleet_query.csv',
                    }
                return jsonify({
                    'matches': matches,
                    'count': len(matches),
                    'total': len(devices),
                    'expression': expression,
                })
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                logger.error(f"Fleet query error: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/fleet/query/validate', methods=['POST'])
        def fleet_query_validate():
            """Validate a query expression without executing it."""
            data = request.get_json(silent=True) or {}
            expression = data.get('expression', '')
            if not expression:
                return jsonify({'error': 'expression required'}), 400
            return jsonify(client.validate_query(expression))

        @app.route('/fleet/query/fields')
        def fleet_query_fields():
            """Return supported query fields with descriptions."""
            return jsonify({'fields': client.get_query_fields()})

        @app.route('/fleet/query/presets')
        def fleet_query_presets():
            """Return built-in preset queries."""
            return jsonify({'presets': client.get_preset_queries()})

        @app.route('/fleet/queries', methods=['GET'])
        def fleet_saved_queries_list():
            return jsonify({'queries': client.list_saved_queries()})

        @app.route('/fleet/queries', methods=['POST'])
        def fleet_saved_queries_create():
            data = request.get_json(silent=True) or {}
            name = data.get('name', '').strip()
            expression = data.get('expression', '').strip()
            description = data.get('description', '')
            if not name or not expression:
                return jsonify({'error': 'name and expression required'}), 400
            try:
                query = client.create_saved_query(name, expression, description)
                return jsonify(query), 201
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        @app.route('/fleet/queries/<query_id>', methods=['GET'])
        def fleet_saved_query_get(query_id):
            query = client.get_saved_query(query_id)
            if not query:
                return jsonify({'error': 'Query not found'}), 404
            return jsonify(query)

        @app.route('/fleet/queries/<query_id>', methods=['PUT'])
        def fleet_saved_query_update(query_id):
            data = request.get_json(silent=True) or {}
            try:
                query = client.update_saved_query(query_id, data)
                if not query:
                    return jsonify({'error': 'Query not found'}), 404
                return jsonify(query)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        @app.route('/fleet/queries/<query_id>', methods=['DELETE'])
        def fleet_saved_query_delete(query_id):
            deleted = client.delete_saved_query(query_id)
            if not deleted:
                return jsonify({'error': 'Query not found'}), 404
            return jsonify({'deleted': True})

        @app.route('/fleet/query/bulk-action', methods=['POST'])
        def fleet_query_bulk_action():
            """Execute a bulk action on devices matching a query."""
            data = request.get_json(silent=True) or {}
            expression = data.get('expression', '').strip()
            action = data.get('action', '').strip()
            action_params = data.get('params', {})

            if not expression or not action:
                return jsonify({'error': 'expression and action required'}), 400

            supported_actions = [
                'reboot', 'lock', 'unlock', 'install_apk',
                'run_automation', 'add_tag', 'remove_tag', 'add_to_group',
            ]
            if action not in supported_actions:
                return jsonify({'error': f'Unsupported action: {action}', 'supported': supported_actions}), 400

            try:
                devices = _get_all_devices()
                matches = client.execute_fleet_query(expression, devices=devices)
                results = []
                for device in matches:
                    did = device.get('device_id') or device.get('serial')
                    result = {'device_id': did, 'action': action, 'success': False}
                    try:
                        if action == 'reboot':
                            client.run_adb_command(['reboot'], device=did)
                            result['success'] = True
                        elif action == 'lock':
                            client.lock_device(did)
                            result['success'] = True
                        elif action == 'unlock':
                            client.unlock_device(did)
                            result['success'] = True
                        elif action == 'install_apk':
                            apk_path = action_params.get('apk_path', '')
                            if apk_path:
                                client.run_adb_command(['install', '-r', apk_path], device=did)
                                result['success'] = True
                            else:
                                result['error'] = 'apk_path required'
                        elif action == 'run_automation':
                            auto_id = action_params.get('automation_id', '')
                            if auto_id:
                                run = client.run_automation(auto_id, device=did)
                                result['success'] = True
                                result['run_id'] = run.get('id')
                            else:
                                result['error'] = 'automation_id required'
                        elif action == 'add_tag':
                            tag = action_params.get('tag', '')
                            if tag:
                                client.add_device_tag(did, tag)
                                result['success'] = True
                            else:
                                result['error'] = 'tag required'
                        elif action == 'remove_tag':
                            tag = action_params.get('tag', '')
                            if tag:
                                client.remove_device_tag(did, tag)
                                result['success'] = True
                            else:
                                result['error'] = 'tag required'
                        elif action == 'add_to_group':
                            group_id = action_params.get('group_id', '')
                            if group_id:
                                client.add_device_to_group(group_id, did)
                                result['success'] = True
                            else:
                                result['error'] = 'group_id required'
                    except Exception as e:
                        result['error'] = str(e)
                    results.append(result)

                succeeded = sum(1 for r in results if r['success'])
                return jsonify({
                    'results': results,
                    'total_matched': len(matches),
                    'succeeded': succeeded,
                    'failed': len(matches) - succeeded,
                })
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                logger.error(f"Bulk action error: {e}")
                return jsonify({'error': str(e)}), 500

        # -----------------------------------------------------------
        # Debug Bundles
        # -----------------------------------------------------------

        @app.route('/devices/<device_id>/debug-bundle', methods=['POST'])
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

        @app.route('/debug-bundles')
        def list_debug_bundles():
            """List all debug bundles with optional filters."""
            device_id = request.args.get('device_id')
            trigger = request.args.get('trigger')
            limit = int(request.args.get('limit', 50))
            bundles = client.list_debug_bundles(device_id=device_id, trigger=trigger, limit=limit)
            return jsonify({'bundles': bundles, 'count': len(bundles)})

        @app.route('/debug-bundles/<bundle_id>')
        def get_debug_bundle(bundle_id):
            """Get debug bundle metadata."""
            bundle = client.get_debug_bundle(bundle_id)
            if not bundle:
                return jsonify({'error': 'Bundle not found'}), 404
            return jsonify(bundle)

        @app.route('/debug-bundles/<bundle_id>/download')
        def download_debug_bundle(bundle_id):
            """Download debug bundle as ZIP."""
            zip_data = client.get_bundle_zip(bundle_id)
            if not zip_data:
                return jsonify({'error': 'Bundle not found'}), 404
            from flask import send_file
            return send_file(
                io.BytesIO(zip_data),
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'debug-bundle-{bundle_id[:8]}.zip',
            )

        @app.route('/debug-bundles/<bundle_id>/analyze', methods=['POST'])
        def analyze_debug_bundle(bundle_id):
            """Trigger AI analysis of a debug bundle."""
            result = client.analyze_debug_bundle(bundle_id)
            if result is None:
                return jsonify({'error': 'Bundle not found'}), 404
            if result.get('error'):
                return jsonify(result), 500
            return jsonify(result)

        @app.route('/debug-bundles/<bundle_id>/share', methods=['POST'])
        def share_debug_bundle(bundle_id):
            """Generate a shareable link for a debug bundle."""
            data = request.get_json(silent=True) or {}
            hours = int(data.get('expires_hours', 24))
            result = client.generate_share_link(bundle_id, expires_hours=hours)
            if not result:
                return jsonify({'error': 'Bundle not found'}), 404
            return jsonify(result), 201

        @app.route('/debug-bundles/share/<token>')
        def download_shared_bundle(token):
            """Download a debug bundle via share token."""
            zip_data, error = client.get_bundle_by_share_token(token)
            if error:
                return jsonify({'error': error}), 403 if 'expired' in error.lower() else 404
            if not zip_data:
                return jsonify({'error': 'Bundle data not available'}), 404
            from flask import send_file
            return send_file(
                io.BytesIO(zip_data),
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'debug-bundle-shared.zip',
            )

        @app.route('/debug-bundles/<bundle_id>', methods=['DELETE'])
        def delete_debug_bundle(bundle_id):
            """Delete a debug bundle."""
            deleted = client.delete_debug_bundle(bundle_id)
            if not deleted:
                return jsonify({'error': 'Bundle not found'}), 404
            return jsonify({'deleted': True})

        # Run
        app.run(host=host, port=port, debug=debug)
        return app
