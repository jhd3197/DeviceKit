"""Data model for devicekit-browser.

Three ``ext_devicekit_browser_*`` tables (prefix required by the platform):

* ``sessions`` — one row per device with an open CDP session (serial, forwarded port,
  page target, busy flag, timestamps). Concurrency is 1 per device (one Chrome per phone).
* ``pools`` — named device sets + a dispatch strategy; ``cursor`` persists round-robin so
  rotation survives a restart.
* ``sticky`` — session tokens that pin a multi-step flow to one device until released/expired.
"""
from sqlalchemy import Table, Column, String, Float, Integer, Text

_PREFIX = "ext_devicekit_browser_"
_tables = {}


def register(db):
    """Called at activation. Defines the tables on the shared metadata (idempotent)."""
    md = db.Base.metadata
    defs = {
        "sessions": lambda: Table(
            _PREFIX + "sessions", md,
            Column("device_id", String, primary_key=True),
            Column("serial", String),
            Column("port", Integer),
            Column("target_id", String),
            Column("busy", Integer, default=0),
            Column("created_at", Float),
            Column("last_used", Float),
        ),
        "pools": lambda: Table(
            _PREFIX + "pools", md,
            Column("name", String, primary_key=True),
            Column("spec_type", String),          # list | all | fql
            Column("spec_value", Text),           # JSON serial list, or FQL string, or ''
            Column("strategy", String),           # round_robin | random | least_recently_used
            Column("cursor", Integer, default=0),
            Column("created_at", Float),
            Column("updated_at", Float),
        ),
        "sticky": lambda: Table(
            _PREFIX + "sticky", md,
            Column("token", String, primary_key=True),
            Column("device_id", String),
            Column("pool", String),
            Column("created_at", Float),
            Column("expires_at", Float),
        ),
    }
    for key, factory in defs.items():
        full = _PREFIX + key
        _tables[key] = md.tables[full] if full in md.tables else factory()
    return _tables


def table(key):
    if key not in _tables:
        raise RuntimeError(f"browser table '{key}' not registered yet")
    return _tables[key]
