"""Queue-driven delivery for async notification channels (plan 06.2).

The producer plans a ``pending`` :class:`NotificationDelivery` row per enabled async channel
and enqueues one ``notification.deliver`` job carrying its ``delivery_id``. This handler —
registered as that job kind by :class:`NotificationsMixin` — renders the channel payload and
transmits it, mapping the outcome back onto the delivery row:

* success → ``sent`` (with ``sent_at``);
* failure → record the error and **raise**, so the Queue Bus retries with backoff and
  dead-letters after ``max_attempts`` (the job then ends failed and the delivery stays
  ``failed`` with the last error — visible in history).

Runs on the shared :class:`~devicekit.jobs.consumer.JobConsumer` worker pool; no channel-
specific daemon. ``process`` is safe to call synchronously (the test-suite does).
"""
import logging
import time

from devicekit.notifications.service import NotificationService
from devicekit.notifications.config import NotificationChannelService
from devicekit.notifications.channels import webhook
from devicekit.models.notification import NotificationDelivery

logger = logging.getLogger(__name__)

DELIVER_JOB_KIND = "notification.deliver"


def deliver(job):
    """Job handler for ``notification.deliver``. ``job`` is the plain job dict; its payload
    carries ``delivery_id``. Returns a compact result on success; raises on a delivery failure
    so the queue retries."""
    payload = job.get("payload", {}) if isinstance(job, dict) else {}
    delivery_id = payload.get("delivery_id")
    if not delivery_id:
        return {"skipped": "missing delivery_id"}

    delivery = NotificationService.get_delivery(delivery_id)
    if not delivery:
        return {"skipped": "delivery missing"}
    if delivery["status"] == NotificationDelivery.STATUS_SENT:
        return {"skipped": "already sent"}

    channel = delivery["channel"]
    notif = NotificationService.get(delivery["notification_id"])
    if not notif:
        NotificationService.mark_delivery(
            delivery_id, status=NotificationDelivery.STATUS_SKIPPED,
            error="Notification vanished")
        return {"skipped": "notification missing"}

    cfg = NotificationChannelService.get(channel)
    if not cfg["enabled"]:
        NotificationService.mark_delivery(
            delivery_id, status=NotificationDelivery.STATUS_SKIPPED,
            error="Channel disabled")
        return {"skipped": "channel disabled"}

    config = cfg["config"]
    NotificationService.mark_delivery(delivery_id, inc_attempts=True)

    try:
        if channel == webhook.CHANNEL:
            body = webhook.render(notif, fmt=config.get("format", "slack"))
            webhook.transmit(config.get("url"), body)
        elif channel == "email":
            from devicekit.notifications.channels import email
            email.send(notif, config)
        else:
            NotificationService.mark_delivery(
                delivery_id, status=NotificationDelivery.STATUS_SKIPPED,
                error=f"Unknown channel {channel}")
            return {"skipped": f"unknown channel {channel}"}
    except Exception as e:
        logger.warning("Delivery %s via %s failed: %s", delivery_id, channel, e)
        NotificationService.mark_delivery(
            delivery_id, status=NotificationDelivery.STATUS_FAILED, error=str(e)[:500])
        raise  # let the Queue Bus retry / dead-letter

    NotificationService.mark_delivery(
        delivery_id, status=NotificationDelivery.STATUS_SENT, error="", sent_at=time.time())
    return {"delivered": channel, "notification_id": notif["id"]}
