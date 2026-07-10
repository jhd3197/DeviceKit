"""Boot-time schema preparation, mirroring ServerKit's ``check_and_prepare`` pattern.

Runs before any data-owning mixin touches the DB:

* Fresh / legacy DB (no ``alembic_version`` table): create every table from the models and
  stamp it at ``head`` so future migrations apply cleanly.
* Managed DB (``alembic_version`` present): upgrade to ``head``.

Keeping Alembic wired from day one means later plans (jobs, extensions, metrics) can add
tables with a normal migration instead of a schema rewrite.
"""
import os
import logging

from sqlalchemy import inspect

from devicekit import db

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC_INI = os.path.join(_BACKEND_DIR, "alembic.ini")


def _alembic_config():
    from alembic.config import Config

    cfg = Config(_ALEMBIC_INI)
    # Point Alembic at the same URL the app uses, regardless of what alembic.ini says.
    cfg.set_main_option("sqlalchemy.url", db.get_database_url())
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    return cfg


def check_and_prepare():
    """Ensure the schema is present and current. Safe to call on every boot."""
    engine = db.get_engine()
    try:
        from alembic import command
    except ImportError:
        # Alembic unavailable — fall back to a plain create_all so the app still runs.
        logger.warning("Alembic not installed; falling back to create_all()")
        db.create_all()
        return

    insp = inspect(engine)
    has_alembic = "alembic_version" in insp.get_table_names()
    cfg = _alembic_config()

    if has_alembic:
        logger.info("Applying database migrations (alembic upgrade head)")
        command.upgrade(cfg, "head")
    else:
        # Fresh or pre-Alembic DB: build the current schema, then stamp so Alembic
        # treats it as up to date.
        logger.info("Preparing database schema (create_all + stamp head)")
        db.create_all()
        command.stamp(cfg, "head")
