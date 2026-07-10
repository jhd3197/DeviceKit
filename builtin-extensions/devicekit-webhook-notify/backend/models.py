"""Data model for the webhook notifier.

Tables an extension owns MUST be prefixed ``ext_<slug>_*`` (dashes -> underscores), so this
one is ``ext_devicekit_webhook_notify_deliveries``. It is defined on the shared metadata
via SQLAlchemy Core so the host can create it at install and drop it on ``uninstall?purge``.
"""
from sqlalchemy import Table, Column, String, Float, Integer, Text

_TABLE_NAME = "ext_devicekit_webhook_notify_deliveries"
_table = None


def register(db):
    """Called at activation. Defines the deliveries table on the shared metadata (idempotent)."""
    global _table
    md = db.Base.metadata
    if _TABLE_NAME in md.tables:
        _table = md.tables[_TABLE_NAME]
    else:
        _table = Table(
            _TABLE_NAME, md,
            Column("id", String, primary_key=True),
            Column("text", Text),
            Column("status_code", Integer),
            Column("error", Text),
            Column("sent_at", Float),
        )
    return _table


def deliveries_table():
    if _table is None:
        raise RuntimeError("deliveries table not registered yet")
    return _table
