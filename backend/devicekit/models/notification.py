"""Notification models (plan 06).

``Notification`` is one rendered event occurrence — title/body/severity/deep-link already
computed at send time (so a route refactor never breaks an old notification) plus the raw
``data`` for re-rendering elsewhere. Read/unread lives here; DeviceKit is single-operator in
dev, so ``recipient`` defaults to ``"default"`` but the column is present for when multi-user
lands.

``NotificationDelivery`` is one row per channel attempt (in-app / webhook / email). The
in-app channel is written ``sent`` immediately; async channels (webhook/email, plans 06.2/3)
start ``pending`` and a queue-driven consumer transmits + updates status, so history survives
a restart and failures are visible.

Timestamps are epoch seconds (``time.time()``) to match the rest of the DeviceKit API
(``alerts``, ``bundles``), not the DateTime convention the job system uses internally.
"""
import time
import uuid

from sqlalchemy import Column, String, Float, Text, Boolean, Integer, JSON, Index

from devicekit.db import Base


class Notification(Base):
    __tablename__ = "notifications"

    SEVERITIES = ("info", "warning", "critical")

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_key = Column(String(100), nullable=False, index=True)
    title = Column(Text, nullable=False)
    body = Column(Text, default="")
    severity = Column(String(20), default="info", index=True)
    category = Column(String(40), default="general")
    deep_link = Column(String(500), default="")

    # What the notification is about, for grouping and dedup.
    subject_type = Column(String(40), nullable=True)
    subject_id = Column(String(128), nullable=True, index=True)

    recipient = Column(String(80), default="default", index=True)
    data = Column(JSON, default=dict)

    read = Column(Boolean, default=False, index=True)
    read_at = Column(Float, nullable=True)
    created_at = Column(Float, default=time.time, index=True)

    __table_args__ = (
        Index("ix_notifications_recipient_read", "recipient", "read"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_key": self.event_key,
            "title": self.title,
            "body": self.body or "",
            "severity": self.severity,
            "category": self.category,
            "deep_link": self.deep_link or "",
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "recipient": self.recipient,
            "data": self.data or {},
            "read": bool(self.read),
            "read_at": self.read_at,
            "created_at": self.created_at,
        }


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id = Column(String(36), nullable=False, index=True)
    channel = Column(String(30), nullable=False, index=True)  # inapp | webhook | email
    status = Column(String(20), default=STATUS_PENDING, index=True)
    target = Column(String(500), default="")                  # webhook URL / email address
    attempts = Column(Integer, default=0)
    error = Column(Text, default="")
    job_id = Column(String(36), nullable=True)                # async delivery job (plan 06.2)
    created_at = Column(Float, default=time.time)
    sent_at = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "notification_id": self.notification_id,
            "channel": self.channel,
            "status": self.status,
            "target": self.target or "",
            "attempts": self.attempts or 0,
            "error": self.error or "",
            "job_id": self.job_id,
            "created_at": self.created_at,
            "sent_at": self.sent_at,
        }


class NotificationChannelConfig(Base):
    """Per-channel delivery configuration (plan 06.2/06.3).

    One row per async channel (``webhook`` / ``email``). ``config`` is a free-form JSON blob
    whose channel-declared secret keys (webhook URL, SMTP password) are stored *encrypted*
    (``enc:`` prefixed) — the service layer encrypts on write and decrypts on read, and masks
    them out of API responses entirely.
    """
    __tablename__ = "notification_channels"

    channel = Column(String(30), primary_key=True)   # webhook | email
    enabled = Column(Boolean, default=False)
    config = Column(JSON, default=dict)
    updated_at = Column(Float, default=time.time)

    def to_dict(self):
        return {
            "channel": self.channel,
            "enabled": bool(self.enabled),
            "config": self.config or {},
            "updated_at": self.updated_at,
        }
