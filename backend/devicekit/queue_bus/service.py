"""SQL-backed Queue Bus for DeviceKit — SQS semantics on the database.

A faithful port of ServerKit's ``QueueBusService`` + ``SQLAlchemyBroker``, collapsed into
one façade and re-plumbed onto DeviceKit's persistence layer: every operation runs in a
short-lived ``session_scope`` (no Flask-SQLAlchemy global session, no ``Model.query``).

Semantics preserved from ServerKit:

* status lifecycle pending → in_flight → completed / failed / dead_letter
* priority ordering, delayed delivery (``visible_after``)
* **visibility timeout** (``invisible_until``) so a crashed consumer's in-flight message
  reappears for redelivery
* ``attempts`` / ``max_attempts`` with exponential backoff, dead-letter on exhaustion

DeviceKit is single-process, so a module-level lock serializes the claim in ``receive`` —
SQLite ignores ``SELECT ... FOR UPDATE``, and this keeps two worker threads from grabbing
the same message. No Redis, no RabbitMQ.
"""
import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import or_, func

from devicekit.db import session_scope
from devicekit.queue_bus.models import QueueGroup, Queue, QueueMessage

logger = logging.getLogger(__name__)

# Serializes receive() claims across worker threads (single-process broker).
_RECEIVE_LOCK = threading.Lock()


class QueueBusError(Exception):
    """Domain error for queue operations."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _valid_slug(slug):
    """Slugs are lowercase alphanumeric plus hyphen/underscore."""
    if not slug:
        return False
    if slug.startswith("-") or slug.startswith("_"):
        return False
    return all(c.isalnum() or c in "-_" for c in slug)


class QueueBusService:
    """Single entry point used by the job system and (later) the extension SDK."""

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------
    @classmethod
    def create_group(cls, slug, name=None, description=None, owner_type="system",
                     owner_id=None, config=None):
        if not _valid_slug(slug):
            raise QueueBusError("Invalid group slug", 400)
        with session_scope() as s:
            if s.query(QueueGroup).filter_by(slug=slug).first():
                raise QueueBusError("Group already exists", 409)
            group = QueueGroup(
                slug=slug, name=name or slug, description=description,
                owner_type=owner_type, owner_id=owner_id,
            )
            group.set_config(config or {})
            s.add(group)
            s.flush()
            return group.to_dict()

    @classmethod
    def get_group(cls, slug):
        with session_scope() as s:
            group = s.query(QueueGroup).filter_by(slug=slug).first()
            return group.to_dict() if group else None

    @classmethod
    def list_groups(cls, limit=100, offset=0):
        with session_scope() as s:
            groups = (s.query(QueueGroup).order_by(QueueGroup.created_at.desc())
                      .limit(limit).offset(offset).all())
            return [g.to_dict() for g in groups]

    # ------------------------------------------------------------------
    # Queues
    # ------------------------------------------------------------------
    @classmethod
    def create_queue(cls, group_slug, slug, name=None, description=None, config=None):
        if not _valid_slug(slug):
            raise QueueBusError("Invalid queue slug", 400)
        with session_scope() as s:
            group = s.query(QueueGroup).filter_by(slug=group_slug).first()
            if not group:
                raise QueueBusError("Group not found", 404)
            if s.query(Queue).filter_by(group_id=group.id, slug=slug).first():
                raise QueueBusError("Queue already exists in group", 409)
            queue = Queue(group_id=group.id, slug=slug, name=name or slug, description=description)
            queue.set_config(config or {})
            s.add(queue)
            s.flush()
            return queue.to_dict()

    @classmethod
    def get_queue(cls, group_slug, queue_slug):
        with session_scope() as s:
            queue = cls._queue_row(s, group_slug, queue_slug)
            return queue.to_dict(session=s) if queue else None

    @classmethod
    def list_queues(cls, group_slug, limit=100, offset=0):
        with session_scope() as s:
            group = s.query(QueueGroup).filter_by(slug=group_slug).first()
            if not group:
                raise QueueBusError("Group not found", 404)
            queues = (s.query(Queue).filter_by(group_id=group.id)
                      .order_by(Queue.created_at.desc()).limit(limit).offset(offset).all())
            return [q.to_dict(session=s) for q in queues]

    @classmethod
    def ensure_queue(cls, group_slug, queue_slug, config=None):
        """Idempotently ensure a group and queue exist. Used by the job system at boot."""
        if cls.get_group(group_slug) is None:
            try:
                cls.create_group(group_slug, name=group_slug.replace("-", " ").title())
            except QueueBusError as e:
                if e.status_code != 409:
                    raise
        if cls.get_queue(group_slug, queue_slug) is None:
            try:
                return cls.create_queue(
                    group_slug, queue_slug,
                    name=queue_slug.replace("-", " ").title(), config=config)
            except QueueBusError as e:
                if e.status_code != 409:
                    raise
        return cls.get_queue(group_slug, queue_slug)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    @classmethod
    def send(cls, group_slug, queue_slug, payload, priority=0, delay_ms=0, max_attempts=None):
        with session_scope() as s:
            queue = cls._queue_row_or_raise(s, group_slug, queue_slug)
            visible_after = datetime.utcnow()
            if delay_ms:
                visible_after += timedelta(milliseconds=delay_ms)
            message_max_attempts = max_attempts or queue.get_config().get("max_attempts", 3)
            message = QueueMessage(
                queue_id=queue.id, group_id=queue.group_id,
                status=QueueMessage.STATUS_PENDING, priority=priority,
                max_attempts=message_max_attempts, visible_after=visible_after,
            )
            message.set_payload(payload)
            s.add(message)
            s.flush()
            return message.to_dict()

    @classmethod
    def receive(cls, group_slug, queue_slug, visibility_timeout_ms=30000, max_messages=1):
        """Claim up to ``max_messages`` visible pending messages, flipping them to in_flight
        with a fresh visibility deadline. Serialized process-wide so concurrent workers never
        double-claim on SQLite."""
        with _RECEIVE_LOCK:
            with session_scope() as s:
                queue = cls._queue_row_or_raise(s, group_slug, queue_slug)
                now = datetime.utcnow()
                invisible_until = now + timedelta(milliseconds=visibility_timeout_ms)
                messages = (
                    s.query(QueueMessage)
                    .filter(
                        QueueMessage.queue_id == queue.id,
                        QueueMessage.status == QueueMessage.STATUS_PENDING,
                        QueueMessage.visible_after <= now,
                        or_(
                            QueueMessage.invisible_until.is_(None),
                            QueueMessage.invisible_until <= now,
                        ),
                    )
                    .order_by(QueueMessage.priority.desc(), QueueMessage.created_at.asc())
                    .limit(max_messages)
                    .all()
                )
                for message in messages:
                    message.status = QueueMessage.STATUS_IN_FLIGHT
                    message.invisible_until = invisible_until
                    message.attempts += 1
                s.flush()
                return [m.to_dict() for m in messages]

    @classmethod
    def complete(cls, group_slug, queue_slug, message_id):
        with session_scope() as s:
            message = cls._message_row_or_raise(s, group_slug, queue_slug, message_id)
            message.status = QueueMessage.STATUS_COMPLETED
            message.completed_at = datetime.utcnow()
            message.invisible_until = None
            s.flush()
            return message.to_dict()

    @classmethod
    def fail(cls, group_slug, queue_slug, message_id, error_message=None, requeue=False):
        with session_scope() as s:
            message = cls._message_row_or_raise(s, group_slug, queue_slug, message_id)
            if error_message:
                stamp = f"[{datetime.utcnow().isoformat()}] {error_message}\n"
                message.error_message = (message.error_message or "") + stamp

            if requeue:
                message.status = QueueMessage.STATUS_PENDING
                message.invisible_until = None
            elif message.attempts >= message.max_attempts:
                message.status = QueueMessage.STATUS_DEAD_LETTER
                message.invisible_until = None
            else:
                # Exponential backoff: 10s, 30s, 90s, ...
                delay_seconds = 10 * (3 ** (message.attempts - 1))
                message.status = QueueMessage.STATUS_PENDING
                message.visible_after = datetime.utcnow() + timedelta(seconds=delay_seconds)
                message.invisible_until = None
            s.flush()
            return message.to_dict()

    @classmethod
    def requeue(cls, group_slug, queue_slug, message_id):
        with session_scope() as s:
            message = cls._message_row_or_raise(s, group_slug, queue_slug, message_id)
            if message.status not in (QueueMessage.STATUS_FAILED, QueueMessage.STATUS_DEAD_LETTER):
                raise QueueBusError("Only failed or dead-letter messages can be requeued", 400)
            message.status = QueueMessage.STATUS_PENDING
            message.visible_after = datetime.utcnow()
            message.invisible_until = None
            s.flush()
            return message.to_dict()

    @classmethod
    def delete_message(cls, group_slug, queue_slug, message_id):
        with session_scope() as s:
            message = cls._message_row_or_raise(s, group_slug, queue_slug, message_id)
            s.delete(message)
        return {"success": True}

    @classmethod
    def get_message(cls, group_slug, queue_slug, message_id):
        with session_scope() as s:
            message = cls._message_row(s, group_slug, queue_slug, message_id)
            return message.to_dict() if message else None

    @classmethod
    def list_messages(cls, group_slug, queue_slug, status=None, limit=100, offset=0):
        with session_scope() as s:
            queue = cls._queue_row_or_raise(s, group_slug, queue_slug)
            q = s.query(QueueMessage).filter_by(queue_id=queue.id)
            if status:
                q = q.filter_by(status=status)
            messages = q.order_by(QueueMessage.created_at.desc()).limit(limit).offset(offset).all()
            return [m.to_dict() for m in messages]

    @classmethod
    def get_stats(cls, group_slug=None, queue_slug=None):
        with session_scope() as s:
            q = s.query(QueueMessage.status, func.count(QueueMessage.id)).group_by(QueueMessage.status)
            if queue_slug:
                queue = cls._queue_row_or_raise(s, group_slug, queue_slug)
                q = q.filter(QueueMessage.queue_id == queue.id)
            elif group_slug:
                group = s.query(QueueGroup).filter_by(slug=group_slug).first()
                if not group:
                    raise QueueBusError("Group not found", 404)
                q = q.filter(QueueMessage.group_id == group.id)
            counts = {st: 0 for st in QueueMessage.ALL_STATUSES}
            for status, count in q.all():
                counts[status] = count
            result = {"messages": counts}
            if queue_slug:
                result["total"] = sum(counts.values())
            return result

    @classmethod
    def reap_expired(cls, group_slug, queue_slug):
        """Return in-flight messages whose visibility deadline lapsed to pending so a
        crashed consumer's work is redelivered. Returns the number reaped. (The receive
        query already treats a lapsed ``invisible_until`` as available; this makes the
        transition explicit for stats/observability and is safe to call periodically.)"""
        with session_scope() as s:
            queue = cls._queue_row(s, group_slug, queue_slug)
            if not queue:
                return 0
            now = datetime.utcnow()
            stale = (s.query(QueueMessage)
                     .filter(QueueMessage.queue_id == queue.id,
                             QueueMessage.status == QueueMessage.STATUS_IN_FLIGHT,
                             QueueMessage.invisible_until.isnot(None),
                             QueueMessage.invisible_until <= now)
                     .all())
            for m in stale:
                m.status = QueueMessage.STATUS_PENDING
                m.invisible_until = None
            return len(stale)

    # ------------------------------------------------------------------
    # Row helpers (operate on a caller-supplied session)
    # ------------------------------------------------------------------
    @staticmethod
    def _queue_row(s, group_slug, queue_slug):
        return (s.query(Queue).join(QueueGroup)
                .filter(QueueGroup.slug == group_slug, Queue.slug == queue_slug).first())

    @classmethod
    def _queue_row_or_raise(cls, s, group_slug, queue_slug):
        queue = cls._queue_row(s, group_slug, queue_slug)
        if not queue:
            raise QueueBusError("Queue not found", 404)
        return queue

    @staticmethod
    def _message_row(s, group_slug, queue_slug, message_id):
        return (s.query(QueueMessage).join(Queue).join(QueueGroup)
                .filter(QueueGroup.slug == group_slug, Queue.slug == queue_slug,
                        QueueMessage.id == message_id).first())

    @classmethod
    def _message_row_or_raise(cls, s, group_slug, queue_slug, message_id):
        message = cls._message_row(s, group_slug, queue_slug, message_id)
        if not message:
            raise QueueBusError("Message not found", 404)
        return message
