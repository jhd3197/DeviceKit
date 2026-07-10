"""Shared pytest fixtures for DeviceKit's persistence tests.

Each test gets an isolated on-disk SQLite database (a real file, so we can simulate a
backend restart by disposing the engine and re-opening the same file). The DB is prepared
through the same ``check_and_prepare`` path the app uses at boot.
"""
import os
import sys
import tempfile
import uuid

import pytest

# Make the backend package importable when pytest is run from the repo root or backend/.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


@pytest.fixture
def db_url(tmp_path):
    """A temp-file SQLite URL unique to the test."""
    path = tmp_path / f"dk_test_{uuid.uuid4().hex}.db"
    return "sqlite:///" + str(path).replace(os.sep, "/")


@pytest.fixture
def fresh_db(db_url):
    """Initialize a clean, migrated database and tear it down afterward."""
    from devicekit import db
    from devicekit.migrate import check_and_prepare

    db.reset()
    db.init_engine(db_url)
    check_and_prepare()
    yield db_url
    db.reset()


@pytest.fixture
def restart():
    """Return a callable that simulates a backend restart: drop the engine and re-open
    the same file, running the (idempotent) boot preparation again."""
    from devicekit import db
    from devicekit.migrate import check_and_prepare

    def _restart(db_url):
        db.reset()
        db.init_engine(db_url)
        check_and_prepare()

    return _restart
