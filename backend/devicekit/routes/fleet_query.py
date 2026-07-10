"""Fleet Query Language routes (query, saved queries, bulk actions)."""
import time
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)


def make_blueprint(client, limiter):
    bp = Blueprint('fleet_query', __name__)

    def _get_all_devices():
        """Helper to get merged ADB + agent device list for queries."""
        connected = client.get_devices()
        adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
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
        return connected

    @bp.route('/fleet/query')
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

    @bp.route('/fleet/query/validate', methods=['POST'])
    def fleet_query_validate():
        """Validate a query expression without executing it."""
        data = request.get_json(silent=True) or {}
        expression = data.get('expression', '')
        if not expression:
            return jsonify({'error': 'expression required'}), 400
        return jsonify(client.validate_query(expression))

    @bp.route('/fleet/query/fields')
    def fleet_query_fields():
        """Return supported query fields with descriptions."""
        return jsonify({'fields': client.get_query_fields()})

    @bp.route('/fleet/query/presets')
    def fleet_query_presets():
        """Return built-in preset queries."""
        return jsonify({'presets': client.get_preset_queries()})

    @bp.route('/fleet/queries', methods=['GET'])
    def fleet_saved_queries_list():
        return jsonify({'queries': client.list_saved_queries()})

    @bp.route('/fleet/queries', methods=['POST'])
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

    @bp.route('/fleet/queries/<query_id>', methods=['GET'])
    def fleet_saved_query_get(query_id):
        query = client.get_saved_query(query_id)
        if not query:
            return jsonify({'error': 'Query not found'}), 404
        return jsonify(query)

    @bp.route('/fleet/queries/<query_id>', methods=['PUT'])
    def fleet_saved_query_update(query_id):
        data = request.get_json(silent=True) or {}
        try:
            query = client.update_saved_query(query_id, data)
            if not query:
                return jsonify({'error': 'Query not found'}), 404
            return jsonify(query)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    @bp.route('/fleet/queries/<query_id>', methods=['DELETE'])
    def fleet_saved_query_delete(query_id):
        deleted = client.delete_saved_query(query_id)
        if not deleted:
            return jsonify({'error': 'Query not found'}), 404
        return jsonify({'deleted': True})

    @bp.route('/fleet/query/bulk-action', methods=['POST'])
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

    return bp
