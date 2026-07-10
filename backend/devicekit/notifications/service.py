"""Notification producer + read/query API (plan 06).

``NotificationService.send(event_key, data, ...)`` is the one entry point a producer calls
(from a job handler, a request handler, or an extension). It:

1. looks the event up in the :mod:`catalog`, rendering title/body/deep-link against ``data``;
2. persists a :class:`Notification` row (durable history that survives restart);
3. delivers through every enabled channel — **in-app is synchronous** (write a ``sent``
   delivery row + push a ``notification`` SSE event), while webhook/email are planned as
   ``pending`` delivery rows and enqueued on the Queue Bus for the async consumer
   (plans 06.2 / 06.3).

Every method returns plain dicts (never ORM rows) because ``session_scope`` closes the
session per operation. ``emit`` is the SSE broadcast callable, injected by
``NotificationsMixin`` so this module stays free of host internals.
"""
import logging
import time

from sqlalchemy import func

from devicekit.db import session_scope
from devicekit.notifications import catalog
from devicekit.notifications.channels import inapp
from devicekit.models.notification import Notification, NotificationDelivery

logger = logging.getLogger(__name__)


class NotificationService:

    # ------------------------------------------------------------------
    # Produce
    # ------------------------------------------------------------------
    @classmethod
    def send(cls, event_key, data=None, recipient="default", subject_type=None,
             subject_id=None, severity=None, emit=None):
        """Create a notification for ``event_key`` and deliver it. Returns the notification
        dict (with its in-app delivery already sent). Never raises for a delivery problem —
        the notification is persisted regardless so history is complete."""
        data = data or {}
        entry = catalog.get(event_key)
        notif = {
            "event_key": event_key,
            "title": entry.render_title(data),
            "body": entry.render_body(data),
            "severity": severity or entry.severity,
            "category": entry.category,
            "deep_link": entry.render_deep_link(data),
            "subject_type": subject_type,
            "subject_id": str(subject_id) if subject_id is not None else None,
            "recipient": recipient,
            "data": data,
        }

        with session_scope() as s:
            row = Notification(
                event_key=notif["event_key"], title=notif["title"], body=notif["body"],
                severity=notif["severity"], category=notif["category"],
                deep_link=notif["deep_link"], subject_type=notif["subject_type"],
                subject_id=notif["subject_id"], recipient=notif["recipient"],
                data=notif["data"], created_at=time.time(),
            )
            s.add(row)
            s.flush()
            notif = row.to_dict()

        # In-app channel: immediate, rides SSE.
        try:
            inapp.deliver(notif, emit)
        except Exception as e:  # observability must never sink a notification
            logger.warning("In-app delivery failed for %s: %s", notif["id"], e)

        # Async channels (webhook/email) are layered in by plans 06.2/06.3.
        try:
            cls._plan_async_channels(notif)
        except Exception as e:
            logger.warning("Async delivery planning failed for %s: %s", notif["id"], e)

        return notif

    @classmethod
    def _plan_async_channels(cls, notif):
        """Hook for webhook/email delivery planning. No-op until plan 06.2 registers async
        channels; kept here so ``send`` has a single, stable shape."""
        return

    # ------------------------------------------------------------------
    # Delivery rows
    # ------------------------------------------------------------------
    @classmethod
    def record_delivery(cls, notification_id, channel, status, target="", error="",
                        attempts=0, job_id=None, sent_at=None):
        with session_scope() as s:
            row = NotificationDelivery(
                notification_id=notification_id, channel=channel, status=status,
                target=target or "", error=error or "", attempts=attempts, job_id=job_id,
                created_at=time.time(),
                sent_at=sent_at if sent_at is not None else (
                    time.time() if status == NotificationDelivery.STATUS_SENT else None),
            )
            s.add(row)
            s.flush()
            return row.to_dict()

    @classmethod
    def list_deliveries(cls, notification_id):
        with session_scope() as s:
            rows = (s.query(NotificationDelivery)
                    .filter(NotificationDelivery.notification_id == notification_id)
                    .order_by(NotificationDelivery.created_at.asc()).all())
            return [r.to_dict() for r in rows]

    # ------------------------------------------------------------------
    # Read / query
    # ------------------------------------------------------------------
    @classmethod
    def list(cls, recipient="default", unread_only=False, severity=None, category=None,
             limit=50, offset=0):
        with session_scope() as s:
            q = s.query(Notification).filter(Notification.recipient == recipient)
            if unread_only:
                q = q.filter(Notification.read.is_(False))
            if severity:
                q = q.filter(Notification.severity == severity)
            if category:
                q = q.filter(Notification.category == category)
            rows = (q.order_by(Notification.created_at.desc())
                    .limit(limit).offset(offset).all())
            return [r.to_dict() for r in rows]

    @classmethod
    def count(cls, recipient="default", unread_only=False):
        with session_scope() as s:
            q = s.query(func.count(Notification.id)).filter(
                Notification.recipient == recipient)
            if unread_only:
                q = q.filter(Notification.read.is_(False))
            return int(q.scalar() or 0)

    @classmethod
    def unread_count(cls, recipient="default"):
        return cls.count(recipient=recipient, unread_only=True)

    @classmethod
    def get(cls, notification_id):
        with session_scope() as s:
            row = s.get(Notification, notification_id)
            return row.to_dict() if row else None

    @classmethod
    def mark_read(cls, notification_id, read=True):
        with session_scope() as s:
            row = s.get(Notification, notification_id)
            if not row:
                return None
            row.read = bool(read)
            row.read_at = time.time() if read else None
            return row.to_dict()

    @classmethod
    def mark_all_read(cls, recipient="default"):
        with session_scope() as s:
            rows = (s.query(Notification)
                    .filter(Notification.recipient == recipient)
                    .filter(Notification.read.is_(False)).all())
            now = time.time()
            for r in rows:
                r.read = True
                r.read_at = now
            return len(rows)

    @classmethod
    def delete(cls, notification_id):
        with session_scope() as s:
            row = s.get(Notification, notification_id)
            if not row:
                return False
            s.query(NotificationDelivery).filter(
                NotificationDelivery.notification_id == notification_id).delete(
                synchronize_session=False)
            s.delete(row)
            return True

    @classmethod
    def clear_all(cls, recipient="default"):
        """Delete every notification for a recipient (and its deliveries). Returns the count."""
        with session_scope() as s:
            ids = [r[0] for r in s.query(Notification.id).filter(
                Notification.recipient == recipient).all()]
            if not ids:
                return 0
            s.query(NotificationDelivery).filter(
                NotificationDelivery.notification_id.in_(ids)).delete(
                synchronize_session=False)
            deleted = s.query(Notification).filter(
                Notification.id.in_(ids)).delete(synchronize_session=False)
            return deleted

    @classmethod
    def prune(cls, retention_days=30, keep_unread=True, batch_size=2000):
        """Delete read notifications older than ``retention_days`` (unread kept if
        ``keep_unread``). Returns the count. Used by a housekeeping schedule."""
        cutoff = time.time() - retention_days * 86400
        deleted = 0
        while True:
            with session_scope() as s:
                q = s.query(Notification.id).filter(Notification.created_at < cutoff)
                if keep_unread:
                    q = q.filter(Notification.read.is_(True))
                ids = [r[0] for r in q.limit(batch_size).all()]
                if not ids:
                    break
                s.query(NotificationDelivery).filter(
                    NotificationDelivery.notification_id.in_(ids)).delete(
                    synchronize_session=False)
                deleted += s.query(Notification).filter(
                    Notification.id.in_(ids)).delete(synchronize_session=False)
            if len(ids) < batch_size:
                break
        return deleted
