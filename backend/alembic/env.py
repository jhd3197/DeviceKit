"""Alembic environment for DeviceKit.

Adds the backend dir to sys.path, pulls the target metadata from ``devicekit.db.Base``
(importing ``devicekit.models`` registers every table), and honors
``DEVICEKIT_DATABASE_URL`` — the same store the app uses.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- make the backend package importable ---
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from devicekit import db  # noqa: E402
import devicekit.models  # noqa: E402,F401 — registers all tables on Base.metadata

config = context.config

# Prefer the app's configured URL unless one was already injected by migrate.py.
if not config.get_main_option("sqlalchemy.url", None) or config.get_main_option(
    "sqlalchemy.url"
) == "sqlite:///devicekit.db":
    try:
        config.set_main_option("sqlalchemy.url", db.get_database_url())
    except Exception:
        pass

if config.config_file_name is not None:
    try:
        # disable_existing_loggers defaults to True, which would silently kill every
        # devicekit.* logger created before the boot-time migration runs.
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except Exception:
        pass

target_metadata = db.Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-friendly ALTERs for future migrations
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
