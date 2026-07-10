"""On-device DeviceKitAgent APK endpoints (register, heartbeat, state, events)."""
import time
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)


def _device_name(client, device_id):
    """A human-friendly label for notifications (the device model), falling back to the id."""
    if not device_id:
        return 'A device'
    try:
        info = (client._agent_device_states.get(device_id) or {}).get('info') or {}
        return info.get('model') or device_id
    except Exception:
        return device_id


def make_blueprint(client, limiter):
    bp = Blueprint('agent_devices', __name__)

    @bp.route('/agent-device/register', methods=['POST'])
    def agent_device_register():
        data = request.get_json(silent=True) or {}
        model = data.get('model', 'unknown')
        manufacturer = data.get('manufacturer', 'unknown')
        device_id = f"{manufacturer}_{model}".replace(' ', '_')
        now = time.time()
        client._agent_device_states[device_id] = {
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
            client._agent_device_serial_index[serial] = device_id
        client.save_agent_device(
            device_id, info=data, serial=serial, registered_at=now,
            last_heartbeat=now, state={}, online=True,
        )
        logger.info(f"Agent device registered: {device_id} (serial={serial})")
        client.log_activity('agent_device_register', device_id, data)
        client.broadcast('device_connected', {'device_id': device_id, 'info': data})
        client.broadcast('device_new', {'device_id': device_id, 'info': data})
        return jsonify({'device_id': device_id, 'status': 'registered'})

    @bp.route('/agent-device/state', methods=['POST'])
    def agent_device_state():
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        if device_id and device_id in client._agent_device_states:
            now = time.time()
            client._agent_device_states[device_id]['state'] = data
            client._agent_device_states[device_id]['last_heartbeat'] = now
            client.update_agent_device_fields(
                device_id, state=data, last_heartbeat=now, online=True,
            )
            client.broadcast('device_state', {'device_id': device_id, 'state': data})

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
                        client.broadcast('alert', alert)
                        if battery < 10:
                            client.notify_event(
                                'device.battery.critical',
                                data={'device_id': device_id,
                                      'device_name': _device_name(client, device_id),
                                      'level': battery},
                                subject_type='device', subject_id=device_id)

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
                        client.broadcast('alert', alert)

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
                            client.broadcast('alert', alert)
                            client.notify_event(
                                'device.storage.low',
                                data={'device_id': device_id,
                                      'device_name': _device_name(client, device_id),
                                      'free_pct': pct, 'free_mb': free},
                                subject_type='device', subject_id=device_id)

        return jsonify({'status': 'ok'})

    @bp.route('/agent-device/heartbeat', methods=['POST'])
    def agent_device_heartbeat():
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        if device_id and device_id in client._agent_device_states:
            now = time.time()
            client._agent_device_states[device_id]['last_heartbeat'] = now
            client._agent_device_states[device_id]['online'] = True
            client.update_agent_device_fields(device_id, last_heartbeat=now, online=True)
            client.broadcast('device_heartbeat', {'device_id': device_id, 'timestamp': now})
        return jsonify({'status': 'ok'})

    @bp.route('/agent-device/event', methods=['POST'])
    def agent_device_event():
        data = request.get_json(silent=True) or {}
        client._agent_device_events.append(data)
        # Keep last 500 events
        if len(client._agent_device_events) > 500:
            client._agent_device_events.pop(0)
        device_id = data.get('device_id', 'unknown')
        event_type = data.get('event', 'unknown')
        logger.info(f"Agent device event: {device_id} -> {event_type}")
        client.broadcast('device_event', data)
        return jsonify({'status': 'ok'})

    @bp.route('/agent-device/<device_id>/commands')
    def agent_device_commands(device_id):
        # Placeholder for command queue from server to on-device agent
        return jsonify({'commands': []})

    @bp.route('/agent-device/<device_id>/metrics')
    def agent_device_metrics(device_id):
        """Return raw agent-sourced metrics for a device."""
        agent_data = client.find_agent_device(device_id)
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

    @bp.route('/agent-device/status')
    def agent_device_status():
        # Mark stale devices as offline (no heartbeat in 15s)
        now = time.time()
        for d in client._agent_device_states.values():
            if now - (d.get('last_heartbeat') or 0) > 15:
                if d.get('online', False):
                    d['online'] = False
                    client.update_agent_device_fields(d.get('device_id'), online=False)
                    client.broadcast('device_disconnected', {'device_id': d.get('device_id')})
                    client.notify_event(
                        'device.offline',
                        data={'device_id': d.get('device_id'),
                              'device_name': _device_name(client, d.get('device_id'))},
                        subject_type='device', subject_id=d.get('device_id'))
        return jsonify({'devices': list(client._agent_device_states.values())})

    @bp.route('/agent-device/events')
    def agent_device_events():
        limit = int(request.args.get('limit', 50))
        return jsonify({'events': client._agent_device_events[-limit:]})

    return bp
