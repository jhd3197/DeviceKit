"""SQLAlchemy engine + session factory for DeviceKit's persistence layer.

DeviceKit is single-process (SSE queues, run threads, and live agent sockets live in
memory), so this module keeps one engine and hands out short-lived sessions — one per
operation — which is the thread-safe pattern the run threads and scheduler need. Durable
state (automations, runs, groups, saved queries, baselines, bundle/session metadata,
agent-device rows) lives in the database; genuinely ephemeral state stays in memory.

Default store is embedded SQLite (`DEVICEKIT_DATABASE_URL`, see config.py); a Postgres
URL is honored verbatim so the same models scale out.
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

# Single declarative base shared by every model module. Import models before calling
# create_all()/Alembic so they register on this metadata.
Base = declarative_base()

_engine = None
_SessionFactory = None


def get_database_url():
    from config import DEVICEKIT_DATABASE_URL
    return DEVICEKIT_DATABASE_URL


def init_engine(database_url=None, echo=False):
    """Create (or replace) the process-wide engine and session factory.

    Idempotent for the common case: passing the same URL twice reuses the existing
    engine. Tests pass an explicit URL (e.g. a temp file or in-memory) to get a fresh DB.
    """
    global _engine, _SessionFactory
    url = database_url or get_database_url()

    connect_args = {}
    if url.startswith("sqlite"):
        # Sessions are created on run threads / the scheduler thread, not just the
        # request thread, so SQLite's same-thread guard must be relaxed.
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        url,
        echo=echo,
        future=True,
        connect_args=connect_args,
    )

    if url.startswith("sqlite"):
        # WAL + a busy timeout keep concurrent readers/writers (run threads + request
        # handlers) from tripping over each other on the single file.
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    _SessionFactory = sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        future=True,
    )
    logger.info(f"Persistence engine initialized ({url.split('://', 1)[0]})")
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def create_all():
    """Create every registered table. Used as the fresh-DB path and by tests."""
    from devicekit import models  # noqa: F401 — ensure all models register on Base
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    """Provide a short-lived transactional session.

    Commits on success, rolls back on exception, always closes. This is the unit of work
    for every mixin operation — never hold a session across steps of a run.
    """
    if _SessionFactory is None:
        init_engine()
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset():
    """Tear down the engine (tests only) so the next init starts clean."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
