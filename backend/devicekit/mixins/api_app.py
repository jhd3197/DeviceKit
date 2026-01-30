import logging
import time
import uuid
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

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
        CORS(app)
        client = self

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
            build_num = len(client._builds) + 1
            build = {
                'id': str(build_num),
                'number': build_num,
                'title': f'Build #{build_num}',
                'status': 'running',
                'created_at': time.time(),
                'success_rate': 0,
                'tests': [],
                'failures': [],
            }
            client._builds.append(build)
            client.log_activity('build_started', details={'build_id': build['id']})
            return jsonify(build), 201

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
            try:
                run_record = client.execute_automation(automation_id, device_id)
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
            result = client.start_agent(device_id, profile)
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

        # -----------------------------------------------------------
        # Agent Device (on-device DeviceKitAgent APK endpoints)
        # -----------------------------------------------------------
        # In-memory store for agent device state
        _agent_device_states = {}
        _agent_device_events = []
        _agent_device_serial_index = {}  # serial -> device_id mapping

        @app.route('/agent-device/register', methods=['POST'])
        def agent_device_register():
            data = request.get_json(silent=True) or {}
            model = data.get('model', 'unknown')
            manufacturer = data.get('manufacturer', 'unknown')
            device_id = f"{manufacturer}_{model}".replace(' ', '_')
            _agent_device_states[device_id] = {
                'device_id': device_id,
                'info': data,
                'registered_at': time.time(),
                'last_heartbeat': time.time(),
                'state': {},
                'online': True,
            }
            # Index by serial number for ADB cross-reference
            serial = data.get('serial')
            if serial:
                _agent_device_serial_index[serial] = device_id
            logger.info(f"Agent device registered: {device_id} (serial={serial})")
            client.log_activity('agent_device_register', device_id, data)
            return jsonify({'device_id': device_id, 'status': 'registered'})

        @app.route('/agent-device/state', methods=['POST'])
        def agent_device_state():
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if device_id and device_id in _agent_device_states:
                _agent_device_states[device_id]['state'] = data
                _agent_device_states[device_id]['last_heartbeat'] = time.time()
            return jsonify({'status': 'ok'})

        @app.route('/agent-device/heartbeat', methods=['POST'])
        def agent_device_heartbeat():
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id')
            if device_id and device_id in _agent_device_states:
                _agent_device_states[device_id]['last_heartbeat'] = time.time()
                _agent_device_states[device_id]['online'] = True
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
                if now - d.get('last_heartbeat', 0) > 15:
                    d['online'] = False
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

        # Run
        app.run(host=host, port=port, debug=debug)
        return app
