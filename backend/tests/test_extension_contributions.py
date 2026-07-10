"""Extension contribution points (plan 03 phase 2): a single extension contributing a step
type, an FQL field, an AI tool, and an ``ext_<slug>_*`` table — registered on install,
bound namespaced into the AI tool registry, deregistered on disable, and re-registered on
enable and after a restart. Plus the declaration-based permission gate."""
import io
import os
import json
import zipfile

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    """Composition with the mixins whose registries extensions contribute to."""


_MODELS_PY = (
    "def register(dbh):\n"
    "    from sqlalchemy import Table, Column, String\n"
    "    md = dbh.Base.metadata\n"
    "    if 'ext_appium_sessions' not in md.tables:\n"
    "        Table('ext_appium_sessions', md, Column('id', String, primary_key=True))\n"
)
_STEPS_PY = (
    "def _run(client, config, device_id):\n"
    "    return 'appium ran ' + config.get('flow', '')\n"
    "def register():\n"
    "    return {'appium.run': {'label': 'Appium Run', 'category': 'Appium',\n"
    "            'config': {'flow': {'type': 'text', 'label': 'Flow', 'required': True}},\n"
    "            'execute': _run}}\n"
)
_FQL_PY = (
    "def register():\n"
    "    return {'appium.session_count': {'resolver': lambda d: 3,\n"
    "            'description': 'Active Appium sessions'}}\n"
)
_TOOLS_PY = (
    "def register(ai):\n"
    "    @ai.tool\n"
    "    def session_count() -> str:\n"
    "        'Return active Appium session count.'\n"
    "        return '3'\n"
)
_ROUTES_PY = (
    "from flask import Blueprint, jsonify\n"
    "bp = Blueprint('appium', __name__)\n"
    "@bp.route('/ping')\n"
    "def ping():\n"
    "    return jsonify({'ok': True})\n"
)


def _full_zip(permissions=("adb", "device.control")):
    manifest = {
        "name": "appium", "display_name": "Appium", "version": "1.0.0",
        "category": "automation", "permissions": list(permissions),
        "entry_point": "routes:bp", "url_prefix": "/extensions/appium",
        "models": "models:register", "step_types": "steps:register",
        "fql_fields": "fql:register", "ai_tools": "tools:register",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", _ROUTES_PY)
        zf.writestr("backend/models.py", _MODELS_PY)
        zf.writestr("backend/steps.py", _STEPS_PY)
        zf.writestr("backend/fql.py", _FQL_PY)
        zf.writestr("backend/tools.py", _TOOLS_PY)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clean_extracted():
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    import shutil
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    # Reset the process-global contribution registries so one test can't leak into another.
    from devicekit.mixins import fleet_query
    for f in list(fleet_query._EXT_FQL_FIELDS):
        fleet_query._EXT_FQL_FIELDS.pop(f, None)
        fleet_query.SUPPORTED_FIELDS.discard(f)
    AutomationMixin._ext_step_types.clear()


def _client(fresh_db):
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def test_contributions_register_on_install(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client(fresh_db)
    client.install_extension_from_zip(_full_zip())

    # Step type appears (metadata JSON-safe) and dispatches through the execute callable.
    st = client.get_step_types()
    assert "appium.run" in st and "execute" not in st["appium.run"]
    assert client._execute_step({"type": "appium.run", "config": {"flow": "smoke"}}, "d") == "appium ran smoke"

    # FQL field resolves + shows up in field metadata.
    from devicekit.mixins.fleet_query import _get_field_value
    assert _get_field_value({}, "appium.session_count", client) == 3
    assert "appium.session_count" in client.get_query_fields()

    # AI tool is bound namespaced <slug>__<name>.
    reg = build_device_tools(client, "d")
    assert "appium__session_count" in reg._tools

    # ext_<slug>_* table was created.
    assert "ext_appium_sessions" in inspect(get_engine()).get_table_names()


def test_permission_gate(fresh_db):
    import devicekit_sdk
    client = _client(fresh_db)
    client.install_extension_from_zip(_full_zip(permissions=("adb",)))

    assert devicekit_sdk.require_permission("appium", "adb") is True
    with pytest.raises(devicekit_sdk.PermissionDenied):
        devicekit_sdk.require_permission("appium", "llm")  # not declared
    # device_control.shell needs adb (declared); screenshot needs device.control (not).
    dc = devicekit_sdk.device_control("appium", "d")
    with pytest.raises(devicekit_sdk.PermissionDenied):
        dc.screenshot()


def test_disable_deregisters_enable_reregisters(fresh_db):
    client = _client(fresh_db)
    client.install_extension_from_zip(_full_zip())

    client.disable_extension("appium")
    assert "appium.run" not in client.get_step_types()
    assert "appium.session_count" not in client.get_query_fields()
    assert "appium__session_count" not in build_device_tools(client, "d")._tools

    client.enable_extension("appium")
    assert "appium.run" in client.get_step_types()
    assert "appium.session_count" in client.get_query_fields()
    assert "appium__session_count" in build_device_tools(client, "d")._tools


def test_contributions_survive_restart(fresh_db, restart):
    client = _client(fresh_db)
    client.install_extension_from_zip(_full_zip())

    restart(fresh_db)

    client2 = _ExtClient()
    client2.init_extensions()
    client2.load_all_extensions(Flask(__name__))
    assert "appium.run" in client2.get_step_types()
    assert "appium.session_count" in client2.get_query_fields()
    assert "appium__session_count" in build_device_tools(client2, "d")._tools


def test_uninstall_purge_drops_ext_tables(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client(fresh_db)
    client.install_extension_from_zip(_full_zip())
    assert "ext_appium_sessions" in inspect(get_engine()).get_table_names()

    client.uninstall_extension("appium", purge=True)
    assert "ext_appium_sessions" not in inspect(get_engine()).get_table_names()
    assert "appium.run" not in client.get_step_types()
