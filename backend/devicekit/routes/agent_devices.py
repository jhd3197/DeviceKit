"""On-device DeviceKitAgent APK endpoints (register, heartbeat, state, events, commands).

Plan 07 routes agent registration through the reconnect-aware registry
(``client.register_agent_device``), drains a real server->agent command queue, accepts
command results back from the agent, and exposes the persisted ``DeviceCommand`` audit
trail. HMAC verification (also plan 07) is applied by ``_require_agent_auth`` when the
device is enrolled; unenrolled/legacy agents keep working unless
``AGENT_ENROLLMENT_REQUIRED`` is set.
"""
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


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr


def make_blueprint(client, limiter):
    bp = Blueprint('agent_devices', __name__)

    def _require_agent_auth(device_id):
        """Verify the HMAC signature for an enrolled device. Returns an error response
        tuple to short-circuit, or ``None`` to proceed.

        The signature is verified *before* the nonce is consumed (ServerKit's subtle fix):
        an attacker who replays a valid nonce with a bad signature can't burn a legitimate
        nonce. Unenrolled devices pass through unless enrollment is globally required.
        """
        try:
            from config import AGENT_ENROLLMENT_REQUIRED
        except Exception:
            AGENT_ENROLLMENT_REQUIRED = False

        creds = client.get_agent_secret(device_id) if device_id else None
        enrolled = bool(creds and creds.get('secret'))
        if not enrolled:
            if AGENT_ENROLLMENT_REQUIRED:
                return jsonify({'error': 'device not enrolled'}), 403
            return None  # legacy/dev path

        ts = request.headers.get('X-Agent-Timestamp', '')
        nonce = request.headers.get('X-Agent-Nonce', '')
        sig = request.headers.get('X-Agent-Signature', '')
        ok, err = client.verify_agent_request(device_id, ts, nonce, sig, ip=_client_ip())
        if not ok:
            return jsonify({'error': err}), 401
        return None

    @bp.route('/agent-device/register', methods=['POST'])
    def agent_device_register():
        data = request.get_json(silent=True) or {}
        model = data.get('model', 'unknown')
        manufacturer = data.get('manufacturer', 'unknown')
        device_id = f"{manufacturer}_{model}".replace(' ', '_')
        serial = data.get('serial')
        capabilities = data.get('capabilities') or {}

        try:
            from config import AGENT_ENROLLMENT_REQUIRED
        except Exception:
            AGENT_ENROLLMENT_REQUIRED = False
        if AGENT_ENROLLMENT_REQUIRED:
            creds = client.get_agent_secret(device_id)
            if not (creds and creds.get('secret')):
                return jsonify({'error': 'device not enrolled; pair first'}), 403
            auth_err = _require_agent_auth(device_id)
            if auth_err:
                return auth_err

        result = client.register_agent_device(
            device_id, info=data, serial=serial, ip=_client_ip(),
            capabilities=capabilities)
        logger.info(f"Agent device registered: {device_id} (serial={serial}, "
                    f"reconnected={result['reconnected']})")
        client.log_activity('agent_device_register', device_id, data)
        client.broadcast('device_connected', {'device_id': device_id, 'info': data})
        if not result['reconnected']:
            client.broadcast('device_new', {'device_id': device_id, 'info': data})
        elif result['was_offline']:
            client.broadcast('device_reconnected', {'device_id': device_id})
            client.notify_event(
                'device.online',
                data={'device_id': device_id, 'device_name': _device_name(client, device_id)},
                subject_type='device', subject_id=device_id)
        return jsonify({'device_id': device_id, 'status': 'registered',
                        'reconnected': result['reconnected']})

    @bp.route('/agent-device/state', methods=['POST'])
    def agent_device_state():
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        if device_id and device_id in client._agent_device_states:
            recovered = client.touch_agent_heartbeat(device_id, state=data, online=True)
            client.broadcast('device_state', {'device_id': device_id, 'state': data})

            # Persist a metrics-history sample from the heartbeat state (plan 08). Cheap, no
            # new polling; threshold alert rules are evaluated inside. Never raises.
            client.record_metrics_sample(device_id, data)

            if recovered:
                client.notify_event(
                    'device.online',
                    data={'device_id': device_id, 'device_name': _device_name(client, device_id)},
                    subject_type='device', subject_id=device_id)

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
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        if device_id and device_id in client._agent_device_states:
            recovered = client.touch_agent_heartbeat(device_id, online=True)
            now = time.time()
            client.broadcast('device_heartbeat', {'device_id': device_id, 'timestamp': now})
            if recovered:
                client.notify_event(
                    'device.online',
                    data={'device_id': device_id, 'device_name': _device_name(client, device_id)},
                    subject_type='device', subject_id=device_id)
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
        """Agent poll: drain the server->agent command queue for this device."""
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        commands = client.drain_outbound_commands(device_id)
        return jsonify({'commands': commands})

    @bp.route('/agent-device/command-result', methods=['POST'])
    def agent_device_command_result():
        """Agent posts the result of a dispatched command back to the waiting caller."""
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        auth_err = _require_agent_auth(device_id)
        if auth_err:
            return auth_err
        command_id = data.get('command_id') or data.get('id')
        if not command_id:
            return jsonify({'error': 'command_id required'}), 400
        ok = client.resolve_device_command(
            command_id, result=data.get('result'), error=data.get('error'))
        if not ok:
            return jsonify({'error': 'unknown command'}), 404
        return jsonify({'status': 'ok'})

    @bp.route('/agent-device/<device_id>/dispatch', methods=['POST'])
    def agent_device_dispatch(device_id):
        """Operator-side: dispatch a command to a device and block for the result. Persisted
        as a DeviceCommand row regardless of outcome (audit trail)."""
        data = request.get_json(silent=True) or {}
        command = data.get('command')
        if not command:
            return jsonify({'error': 'command required'}), 400
        row = client.send_device_command(
            device_id, command, args=data.get('args') or {},
            timeout=data.get('timeout'), source=data.get('source', 'api'))
        code = 200 if row and row['status'] == 'completed' else 202
        return jsonify(row), code

    @bp.route('/agent-device/<device_id>/command-history')
    def agent_device_command_history(device_id):
        limit = int(request.args.get('limit', 100))
        return jsonify({
            'commands': client.list_device_commands(device_id=device_id, limit=limit),
            'count': client.count_device_commands(device_id=device_id),
        })

    @bp.route('/device-commands')
    def device_commands_all():
        """Fleet-wide device-action history."""
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        status = request.args.get('status')
        device_id = request.args.get('device_id')
        return jsonify({
            'commands': client.list_device_commands(
                device_id=device_id, status=status, limit=limit, offset=offset),
            'count': client.count_device_commands(device_id=device_id, status=status),
        })

    # -------------------------------------------------------------------
    # Read-only survey primitives (plan 25 part 1 — the trust boundary)
    # -------------------------------------------------------------------
    @bp.route('/agent-device/primitives')
    def agent_device_primitives():
        """The fixed allowlist of read-only survey primitives the server may compose.

        The panel is untrusted: it can only ask for these primitives (or a named probe that
        combines them) — it can never name a shell command or read a whole file.
        """
        return jsonify(client.list_agent_primitives())

    @bp.route('/agent-device/<device_id>/survey', methods=['POST'])
    def agent_device_survey(device_id):
        """Compose a survey: either a single ``primitive`` (+ ``args``) or a named ``probe``.

        Validation happens before dispatch, so an off-allowlist name is a 400, never a
        command that reaches the device.
        """
        from devicekit.agent_primitives import PrimitiveError
        data = request.get_json(silent=True) or {}
        timeout = data.get('timeout')
        try:
            if data.get('probe'):
                result = client.compose_agent_probe(
                    device_id, data['probe'], timeout=timeout)
                return jsonify(result)
            primitive = data.get('primitive')
            if not primitive:
                return jsonify({'error': 'primitive or probe required'}), 400
            row = client.send_agent_primitive(
                device_id, primitive, args=data.get('args') or {}, timeout=timeout)
            code = 200 if row and row['status'] == 'completed' else 202
            return jsonify(row), code
        except PrimitiveError as e:
            return jsonify({'error': str(e)}), 400

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

    # -------------------------------------------------------------------
    # Enrollment / pairing (plan 07 phase 3)
    # -------------------------------------------------------------------
    @bp.route('/agent-device/enroll', methods=['POST'])
    def agent_device_enroll():
        """Agent starts enrollment; receives a pairing code to display for an operator."""
        data = request.get_json(silent=True) or {}
        result = client.enroll_agent(data, serial=data.get('serial'), ip=_client_ip())
        return jsonify(result)

    @bp.route('/agent-device/enroll/<pairing_id>')
    def agent_device_enroll_poll(pairing_id):
        """Agent polls until an operator claims the code, then gets its secret once."""
        return jsonify(client.poll_enrollment(pairing_id))

    @bp.route('/agent-devices/pending')
    def agent_devices_pending():
        """Dashboard: list agents awaiting a claim."""
        pending = client.list_pending_agents()
        return jsonify({'pending': pending, 'count': len(pending)})

    @bp.route('/agent-devices/claim', methods=['POST'])
    def agent_devices_claim():
        """Dashboard: operator claims a pairing code, enrolling the device."""
        data = request.get_json(silent=True) or {}
        code = data.get('code')
        if not code:
            return jsonify({'error': 'code required'}), 400
        try:
            result = client.claim_pending_agent(code, passphrase=data.get('passphrase'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        client.log_activity('agent_device_claim', result.get('device_id'), result)
        return jsonify(result)

    # -------------------------------------------------------------------
    # Capabilities + key rotation (plan 07 phase 4)
    # -------------------------------------------------------------------
    @bp.route('/agent-device/<device_id>/capabilities')
    def agent_device_capabilities(device_id):
        return jsonify({'device_id': device_id,
                        'capabilities': client.get_agent_capabilities(device_id)})

    @bp.route('/agent-device/<device_id>/rotate-key', methods=['POST'])
    def agent_device_rotate_key(device_id):
        """Start zero-downtime key rotation: stage a new secret (both remain valid until the
        agent confirms and rotation completes)."""
        new_secret = client.start_key_rotation(device_id)
        if new_secret is None:
            return jsonify({'error': 'device not enrolled'}), 404
        client.log_activity('agent_key_rotation_start', device_id, {})
        return jsonify({'device_id': device_id, 'secret': new_secret, 'status': 'rotating'})

    @bp.route('/agent-device/<device_id>/rotate-key/complete', methods=['POST'])
    def agent_device_rotate_key_complete(device_id):
        """Promote the pending secret to active and retire the old one."""
        ok = client.complete_key_rotation(device_id)
        if not ok:
            return jsonify({'error': 'no pending rotation'}), 400
        client.log_activity('agent_key_rotation_complete', device_id, {})
        return jsonify({'device_id': device_id, 'status': 'rotated'})

    @bp.route('/agent-device/status')
    def agent_device_status():
        # The heartbeat reaper owns online->offline transitions (plan 07); run it here too so
        # a status poll reflects reality even between scheduled ticks. Idempotent + lock-guarded.
        client.reap_stale_agents()
        return jsonify({'devices': list(client._agent_device_states.values())})

    @bp.route('/agent-device/events')
    def agent_device_events():
        limit = int(request.args.get('limit', 50))
        return jsonify({'events': client._agent_device_events[-limit:]})

    return bp
