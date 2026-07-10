"""NotificationsMixin — the Client's façade over the notification bus (plan 06).

Owns catalog seeding at boot and the thin methods the ``notifications`` blueprint, the
producer call sites (heartbeat/offline, automation run outcomes, visual regression), and the
extension SDK call. The producer binds the host's SSE ``broadcast`` as the in-app emit, so
the service layer stays free of host internals.

Composed in ``client.py`` before ``ApiAppMixin``; ``init_notifications`` runs after
``init_persistence`` (it registers a housekeeping schedule) and after ``init_jobs`` (so the
prune job kind and schedule can register onto the live job system).
"""
import logging

from devicekit.notifications import catalog
from devicekit.notifications.service import NotificationService

logger = logging.getLogger(__name__)


class NotificationsMixin:
    _notifications_ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_notifications(self):
        """Seed the event catalog and register housekeeping. Idempotent."""
        if self._notifications_ready:
            return
        catalog.seed_default_events()
        # Retention prune + async delivery ride the unified job system when it is available.
        try:
            if hasattr(self, "register_job_kind"):
                from devicekit.notifications.consumer import DELIVER_JOB_KIND, deliver
                self.register_job_kind(DELIVER_JOB_KIND, deliver)
                self.register_job_kind(
                    "notifications.retention.prune", self._job_prune_notifications)
                self.register_job_kind(
                    "notification.digest.flush", self._job_flush_digests)
            if hasattr(self, "ensure_scheduled_job"):
                self.ensure_scheduled_job(
                    "notifications.retention.prune", "notifications.retention.prune",
                    interval_seconds=86400, startup_delay_seconds=3600,
                    owner_type="system", owner_id="core")
                # Digest flush ticks every 5 min; the flush batches whatever markers are due.
                self.ensure_scheduled_job(
                    "notification.digest.flush", "notification.digest.flush",
                    interval_seconds=300, startup_delay_seconds=300,
                    owner_type="system", owner_id="core")
        except Exception as e:
            logger.warning("Notification housekeeping not scheduled: %s", e)
        self._notifications_ready = True
        logger.info("Notification bus initialized (%d catalog events)",
                    len(catalog.all_events()))

    def _job_prune_notifications(self, job):
        payload = job.get("payload", {}) if isinstance(job, dict) else {}
        days = int(payload.get("retention_days", 30))
        return {"pruned": NotificationService.prune(retention_days=days)}

    def _job_flush_digests(self, job):
        from devicekit.notifications.preferences import flush_digests
        return flush_digests()

    # ------------------------------------------------------------------
    # Producer
    # ------------------------------------------------------------------
    def notify_event(self, event_key, data=None, recipient="default", subject_type=None,
                     subject_id=None, severity=None):
        """Emit a notification for ``event_key``. Non-blocking, safe to call from anywhere
        (jobs, request handlers, extensions). Never raises — a notification problem must not
        take down the caller (a run, a heartbeat)."""
        try:
            return NotificationService.send(
                event_key, data=data, recipient=recipient, subject_type=subject_type,
                subject_id=subject_id, severity=severity, emit=self.broadcast)
        except Exception as e:
            logger.warning("notify_event(%s) failed: %s", event_key, e)
            return None

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------
    def list_notification_events(self):
        return catalog.all_events()

    def register_notification_event(self, event_key, title, **kwargs):
        return catalog.register(event_key, title, **kwargs).to_dict()

    # ------------------------------------------------------------------
    # Read / query façade
    # ------------------------------------------------------------------
    def list_notifications(self, recipient="default", unread_only=False, severity=None,
                           category=None, limit=50, offset=0):
        return NotificationService.list(
            recipient=recipient, unread_only=unread_only, severity=severity,
            category=category, limit=limit, offset=offset)

    def count_notifications(self, recipient="default", unread_only=False):
        return NotificationService.count(recipient=recipient, unread_only=unread_only)

    def unread_notification_count(self, recipient="default"):
        return NotificationService.unread_count(recipient=recipient)

    def get_notification(self, notification_id):
        return NotificationService.get(notification_id)

    def get_notification_deliveries(self, notification_id):
        return NotificationService.list_deliveries(notification_id)

    def mark_notification_read(self, notification_id, read=True):
        return NotificationService.mark_read(notification_id, read=read)

    def mark_all_notifications_read(self, recipient="default"):
        return NotificationService.mark_all_read(recipient=recipient)

    def delete_notification(self, notification_id):
        return NotificationService.delete(notification_id)

    def clear_notifications(self, recipient="default"):
        return NotificationService.clear_all(recipient=recipient)

    # ------------------------------------------------------------------
    # Channel configuration (plan 06.2/06.3)
    # ------------------------------------------------------------------
    def list_notification_channels(self):
        from devicekit.notifications.config import NotificationChannelService
        return NotificationChannelService.list_masked()

    def get_notification_channel(self, channel):
        from devicekit.notifications.config import NotificationChannelService
        return NotificationChannelService.get_masked(channel)

    def set_notification_channel(self, channel, enabled=None, config=None):
        from devicekit.notifications.config import NotificationChannelService
        return NotificationChannelService.set(channel, enabled=enabled, config=config)

    # ------------------------------------------------------------------
    # Preferences (plan 06.3)
    # ------------------------------------------------------------------
    def get_notification_settings(self, recipient="default"):
        from devicekit.notifications.preferences import PreferenceService
        return PreferenceService.get_settings(recipient=recipient)

    def update_notification_settings(self, recipient="default", **fields):
        from devicekit.notifications.preferences import PreferenceService
        return PreferenceService.set_settings(recipient=recipient, **fields)

    def list_notification_mutes(self, recipient="default"):
        from devicekit.notifications.preferences import PreferenceService
        return PreferenceService.list_prefs(recipient=recipient)

    def set_notification_mute(self, recipient, event_key, channel=None, muted=True):
        from devicekit.notifications.preferences import PreferenceService
        return PreferenceService.set_pref(recipient, event_key, channel=channel, muted=muted)

    def flush_notification_digests(self):
        from devicekit.notifications.preferences import flush_digests
        return flush_digests()

    def test_notification_channel(self, channel):
        """Synchronously send a sample notification through a channel so the UI can verify
        config immediately (bypasses the queue). Returns ``{'ok': bool, 'error': str}``."""
        from devicekit.notifications.config import NotificationChannelService
        from devicekit.notifications.channels import webhook
        cfg = NotificationChannelService.get(channel)
        config = cfg["config"]
        sample = {
            "id": "test", "event_key": "notification.test",
            "title": "DeviceKit test notification",
            "body": "If you can see this, the channel is configured correctly.",
            "severity": "info", "category": "test", "deep_link": "", "data": {},
        }
        try:
            if channel == "webhook":
                webhook.transmit(config.get("url"),
                                 webhook.render(sample, fmt=config.get("format", "slack")))
            elif channel == "email":
                from devicekit.notifications.channels import email
                email.send(sample, config)
            else:
                return {"ok": False, "error": f"Unknown channel {channel}"}
            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}
