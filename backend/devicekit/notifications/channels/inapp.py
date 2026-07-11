"""In-app notification channel (plan 06.1).

The cheapest, always-on channel: it writes a ``sent`` delivery row and pushes the rendered
notification onto the existing SSE stream as a ``notification`` event, so the frontend bell
lights up without any polling. No Socket.IO — DeviceKit's real-time is SSE.

``deliver`` is synchronous and called inline from ``NotificationService.send``; ``emit`` is
the host's ``broadcast(event_type, data)`` (injected so this module never imports the host).
"""
import logging

from devicekit.models.notification import NotificationDelivery

logger = logging.getLogger(__name__)

CHANNEL = "inapp"


def deliver(notif, emit=None):
    """Record an in-app delivery and broadcast the notification over SSE. Returns the
    delivery dict. Import the service lazily to avoid a circular import at module load."""
    from devicekit.notifications.service import NotificationService

    delivery = NotificationService.record_delivery(
        notif["id"], CHANNEL, NotificationDelivery.STATUS_SENT)

    if emit is not None:
        try:
            emit("notification", notif)
        except Exception as e:  # a broken SSE client must not fail delivery
            logger.debug("SSE emit failed for notification %s: %s", notif["id"], e)

    return delivery
