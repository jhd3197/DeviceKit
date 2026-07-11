"""Data model for devicekit-notification-capture.

One ``ext_devicekit_notification_capture_events`` table (prefix required by the platform):
each captured device notification, deduped by ``dedup_key``.
"""
from sqlalchemy import Table, Column, String, Float, Text, Index

_TABLE_NAME = "ext_devicekit_notification_capture_events"
_table = None


def register(db):
    """Called at activation. Defines the events table on the shared metadata (idempotent)."""
    global _table
    md = db.Base.metadata
    if _TABLE_NAME in md.tables:
        _table = md.tables[_TABLE_NAME]
    else:
        _table = Table(
            _TABLE_NAME, md,
            Column("id", String, primary_key=True),
            Column("device_id", String, index=True),
            Column("package", String),
            Column("title", Text),
            Column("text", Text),
            Column("posted_at", Float),
            Column("dedup_key", String, index=True),
            Column("captured_at", Float),
            Index(f"ix_{_TABLE_NAME}_dev_key", "device_id", "dedup_key"),
        )
    return _table


def events_table():
    if _table is None:
        raise RuntimeError("notification-capture events table not registered yet")
    return _table
