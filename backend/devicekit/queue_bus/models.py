"""ORM models for the DeviceKit Queue Bus.

Ported from ServerKit's ``queue_bus/models.py`` (concept: SQS semantics on a database).
Adapted to DeviceKit's persistence layer: plain SQLAlchemy models on the shared ``Base``
(no Flask-SQLAlchemy), driven through short-lived ``session_scope`` sessions. Timestamps
stay ``DateTime`` (UTC) because the broker's logic — visibility timeouts, delayed delivery,
backoff — is datetime arithmetic; that is internal to the bus and never surfaces in a
frontend envelope.
"""
import json
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from devicekit.db import Base


class QueueGroup(Base):
    """A namespace for related queues."""

    __tablename__ = "queue_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(128), nullable=False, unique=True, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    owner_type = Column(String(32), default="system", nullable=False)
    owner_id = Column(String(128), nullable=True)
    config_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    queues = relationship("Queue", back_populates="group", cascade="all, delete-orphan")

    def get_config(self):
        if self.config_json:
            try:
                return json.loads(self.config_json)
            except (TypeError, json.JSONDecodeError):
                return {}
        return {}

    def set_config(self, value):
        self.config_json = json.dumps(value) if value is not None else None

    def to_dict(self):
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "config": self.get_config(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Queue(Base):
    """A named message pipe inside a QueueGroup."""

    __tablename__ = "queues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("queue_groups.id"), nullable=False, index=True)
    slug = Column(String(128), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    config_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    group = relationship("QueueGroup", back_populates="queues")
    messages = relationship("QueueMessage", back_populates="queue", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("group_id", "slug", name="uix_queue_group_slug"),
    )

    def get_config(self):
        if self.config_json:
            try:
                return json.loads(self.config_json)
            except (TypeError, json.JSONDecodeError):
                return {}
        return {}

    def set_config(self, value):
        self.config_json = json.dumps(value) if value is not None else None

    def to_dict(self, session=None):
        data = {
            "id": self.id,
            "group_id": self.group_id,
            "group_slug": self.group.slug if self.group else None,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "config": self.get_config(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if session is not None:
            base = session.query(QueueMessage.status, func.count(QueueMessage.id)).filter(
                QueueMessage.queue_id == self.id
            ).group_by(QueueMessage.status)
            counts = dict(base.all())
            data["stats"] = {
                st: counts.get(st, 0) for st in QueueMessage.ALL_STATUSES
            }
            data["stats"]["total"] = sum(counts.values())
        return data


class QueueMessage(Base):
    """A single message in a Queue."""

    __tablename__ = "queue_messages"

    STATUS_PENDING = "pending"
    STATUS_IN_FLIGHT = "in_flight"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_DEAD_LETTER = "dead_letter"

    ALL_STATUSES = (
        STATUS_PENDING, STATUS_IN_FLIGHT, STATUS_COMPLETED, STATUS_FAILED, STATUS_DEAD_LETTER,
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String(36), ForeignKey("queues.id"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("queue_groups.id"), nullable=False, index=True)
    status = Column(String(32), default=STATUS_PENDING, nullable=False, index=True)
    priority = Column(Integer, default=0, nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    result_json = Column(Text)
    error_message = Column(Text)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    visible_after = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    invisible_until = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    queue = relationship("Queue", back_populates="messages")
    group = relationship("QueueGroup")

    def get_payload(self):
        if self.payload_json:
            try:
                return json.loads(self.payload_json)
            except (TypeError, json.JSONDecodeError):
                return {}
        return {}

    def set_payload(self, value):
        self.payload_json = json.dumps(value) if value is not None else "{}"

    def get_result(self):
        if self.result_json:
            try:
                return json.loads(self.result_json)
            except (TypeError, json.JSONDecodeError):
                return {}
        return {}

    def set_result(self, value):
        self.result_json = json.dumps(value) if value is not None else None

    def to_dict(self, include_payload=True):
        data = {
            "id": self.id,
            "queue_id": self.queue_id,
            "group_id": self.group_id,
            "group_slug": self.group.slug if self.group else None,
            "queue_slug": self.queue.slug if self.queue else None,
            "status": self.status,
            "priority": self.priority,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "error_message": self.error_message,
            "visible_after": self.visible_after.isoformat() if self.visible_after else None,
            "invisible_until": self.invisible_until.isoformat() if self.invisible_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_payload:
            data["payload"] = self.get_payload()
            data["result"] = self.get_result()
        return data
