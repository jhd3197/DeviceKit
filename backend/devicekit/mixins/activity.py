import uuid
import time
import logging

logger = logging.getLogger(__name__)


class ActivityMixin:
    """Activity logging system."""

    _activities = []

    def log_activity(self, action, device_id=None, details=None, source_ip=None, authenticated=None):
        """Log an activity event."""
        activity = {
            'id': str(uuid.uuid4()),
            'action': action,
            'device_id': device_id,
            'details': details or {},
            'timestamp': time.time(),
            'source_ip': source_ip,
            'authenticated': authenticated,
        }
        self._activities.append(activity)
        logger.info(f"Activity logged: {action}" + (f" on {device_id}" if device_id else ""))
        return activity

    def get_activities(self, limit=50, device_id_filter=None):
        """Get activities with optional device filter."""
        results = self._activities
        if device_id_filter:
            results = [a for a in results if a['device_id'] == device_id_filter]
        results = sorted(results, key=lambda a: a['timestamp'], reverse=True)
        return results[:limit]

    def get_activity_summary(self):
        """Get activity counts grouped by action type."""
        summary = {}
        for activity in self._activities:
            action = activity['action']
            summary[action] = summary.get(action, 0) + 1
        return summary
