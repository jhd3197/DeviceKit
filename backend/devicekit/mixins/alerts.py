import uuid
import time
import logging

logger = logging.getLogger(__name__)

ALERT_TYPES = {'low_battery', 'disconnected', 'error', 'overheating', 'storage_full'}
SEVERITY_LEVELS = {'info', 'warning', 'critical'}


class AlertMixin:
    """Alert management system."""

    _alerts = []

    def create_alert(self, device_id, alert_type, message, severity='warning'):
        """Create a new alert."""
        alert = {
            'id': str(uuid.uuid4()),
            'device_id': device_id,
            'type': alert_type,
            'message': message,
            'severity': severity,
            'status': 'active',
            'created_at': time.time(),
            'dismissed_at': None,
        }
        self._alerts.append(alert)
        logger.info(f"Alert created: {alert_type} for device {device_id}")
        return alert

    def get_alerts(self, limit=50, type_filter=None, status_filter='active'):
        """Get alerts with optional filtering."""
        results = self._alerts
        if type_filter:
            results = [a for a in results if a['type'] == type_filter]
        if status_filter:
            results = [a for a in results if a['status'] == status_filter]
        results = sorted(results, key=lambda a: a['created_at'], reverse=True)
        return results[:limit]

    def dismiss_alert(self, alert_id):
        """Dismiss an alert by ID."""
        for alert in self._alerts:
            if alert['id'] == alert_id:
                alert['status'] = 'dismissed'
                alert['dismissed_at'] = time.time()
                logger.info(f"Alert {alert_id} dismissed")
                return True
        return False

    def check_device_health(self, device_id):
        """Check device health and auto-generate alerts."""
        alerts_generated = []
        try:
            battery = self.get_device_battery(device=device_id)
            level = int(battery.get('level', 100))
            if level < 20:
                alert = self.create_alert(
                    device_id, 'low_battery',
                    f'Battery at {level}%',
                    severity='critical' if level < 10 else 'warning'
                )
                alerts_generated.append(alert)

            temp_str = battery.get('temperature', '0')
            temp = int(temp_str) / 10 if temp_str.isdigit() else 0
            if temp > 45:
                alert = self.create_alert(
                    device_id, 'overheating',
                    f'Temperature at {temp}°C',
                    severity='critical' if temp > 50 else 'warning'
                )
                alerts_generated.append(alert)
        except Exception as e:
            logger.error(f"Health check failed for {device_id}: {e}")

        return alerts_generated
