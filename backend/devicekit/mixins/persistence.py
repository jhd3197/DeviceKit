"""Owns the persistence-layer lifecycle for the Client.

Registered in ``client.py`` *before* every data-owning mixin so the engine and schema are
ready by the time those mixins run. Exposes a short-lived ``session_scope`` for the other
mixins to import directly, and a thin ``db_session()`` convenience on the client.
"""
import logging

from devicekit import db
from devicekit.migrate import check_and_prepare

logger = logging.getLogger(__name__)


class PersistenceMixin:
    """Initializes the SQLAlchemy engine + schema and exposes session helpers."""

    _persistence_ready = False

    def init_persistence(self, database_url=None):
        """Bring up the engine and ensure the schema exists. Idempotent per process."""
        db.init_engine(database_url)
        check_and_prepare()
        self._persistence_ready = True
        logger.info("Persistence layer ready")

    def db_session(self):
        """Return a ``with``-able short-lived session (commits on success, rolls back on
        error). Prefer this for one-off client-level DB work."""
        return db.session_scope()
