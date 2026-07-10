"""Dashboard stats route."""
import time

from flask import Blueprint, jsonify


def make_blueprint(client, limiter):
    bp = Blueprint('dashboard', __name__)

    @bp.route('/dashboard/stats')
    def dashboard_stats():
        connected = client.get_devices()
        # Include agent-registered devices in fleet count
        now = time.time()
        adb_ids = {d.get('serial') or d.get('device_id') for d in connected if d}
        agent_count = 0
        agent_busy = 0
        for agent_id, agent_data in client._agent_device_states.items():
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

    return bp
