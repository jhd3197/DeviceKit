"""Fleet management routes (groups, bulk actions, tags, locking, health, compare)."""
import time

from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('fleet', __name__)

    @bp.route('/fleet/groups')
    def fleet_groups_list():
        groups = client.list_device_groups()
        return jsonify({'groups': groups, 'count': len(groups)})

    @bp.route('/fleet/groups', methods=['POST'])
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

    @bp.route('/fleet/groups/<group_id>')
    def fleet_groups_get(group_id):
        group = client.get_device_group(group_id)
        if group:
            return jsonify(group)
        return jsonify({'error': 'Group not found'}), 404

    @bp.route('/fleet/groups/<group_id>', methods=['PUT'])
    def fleet_groups_update(group_id):
        data = request.get_json(silent=True) or {}
        result = client.update_device_group(group_id, data)
        if result is None:
            return jsonify({'error': 'Group not found'}), 404
        return jsonify(result)

    @bp.route('/fleet/groups/<group_id>', methods=['DELETE'])
    def fleet_groups_delete(group_id):
        if client.delete_device_group(group_id):
            return '', 204
        return jsonify({'error': 'Group not found'}), 404

    @bp.route('/fleet/groups/<group_id>/devices', methods=['POST'])
    def fleet_group_add_device(group_id):
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id', '')
        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400
        result = client.add_device_to_group(group_id, device_id)
        if result is None:
            return jsonify({'error': 'Group not found'}), 404
        return jsonify(result)

    @bp.route('/fleet/groups/<group_id>/devices/<device_id>', methods=['DELETE'])
    def fleet_group_remove_device(group_id, device_id):
        result = client.remove_device_from_group(group_id, device_id)
        if result is None:
            return jsonify({'error': 'Group not found'}), 404
        return jsonify(result)

    # ── Bulk Actions ──
    @bp.route('/fleet/groups/<group_id>/bulk/command', methods=['POST'])
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
        client.broadcast('bulk_action_complete', {
            'group_id': group_id, 'action': 'command', 'results': results,
        })
        return jsonify({'results': results})

    @bp.route('/fleet/groups/<group_id>/bulk/install', methods=['POST'])
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
        client.broadcast('bulk_action_complete', {
            'group_id': group_id, 'action': 'install', 'results': results,
        })
        return jsonify({'results': results})

    @bp.route('/fleet/groups/<group_id>/bulk/reboot', methods=['POST'])
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
        client.broadcast('bulk_action_complete', {
            'group_id': group_id, 'action': 'reboot', 'results': results,
        })
        return jsonify({'results': results})

    # ── Per-Device Tags ──
    @bp.route('/devices/<device_id>/tags')
    def device_tags_get(device_id):
        tags = client.get_device_tags(device_id)
        groups = client.get_groups_for_device(device_id)
        return jsonify({'device_id': device_id, 'tags': tags, 'groups': groups})

    @bp.route('/devices/<device_id>/tags', methods=['PUT'])
    def device_tags_update(device_id):
        data = request.get_json(silent=True) or {}
        tags = data.get('tags', [])
        result = client.set_device_tags(device_id, tags)
        return jsonify({'device_id': device_id, 'tags': result})

    # ── Device Locking ──
    @bp.route('/devices/<device_id>/lock', methods=['POST'])
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

    @bp.route('/devices/<device_id>/unlock', methods=['POST'])
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

    @bp.route('/devices/available')
    def devices_available():
        available = client.get_available_devices()
        return jsonify({'devices': available, 'count': len(available)})

    # ── Fleet Health ──
    @bp.route('/fleet/health')
    def fleet_health():
        connected = client.get_devices()
        now = time.time()
        adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
        for agent_id, agent_data in client._agent_device_states.items():
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

    @bp.route('/fleet/compare')
    def fleet_compare():
        device_ids = request.args.get('devices', '')
        ids = [d.strip() for d in device_ids.split(',') if d.strip()][:4]
        results = []
        for did in ids:
            agent_data = client.find_agent_device(did)
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

    return bp
