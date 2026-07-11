"""devicekit-explorer (plan 15 phase 3): installs, mounts its device-scoped blueprint, binds
gated file AI tools, and publishes frontend contributions (a route page + a node-detail.tabs
widget). File verbs proxy to the on-device agent, so without an online agent they return a
clean 503 — the live file ops are verified against a phone separately.
"""
import os
import shutil

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools

SLUG = "devicekit-explorer"
PKG = SLUG.replace("-", "_")


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    def broadcast(self, *a, **k):
        pass

    def find_agent_device(self, device_id):
        return None  # no online agent in the test harness


@pytest.fixture(autouse=True)
def _clean():
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()


def _client():
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def test_explorer_installs_and_contributes(fresh_db):
    client = _client()
    ext = client.install_builtin_extension(SLUG)
    assert ext["status"] == "active" and ext["source"] == "builtin"

    # Blueprint mounted at /ext/devicekit-explorer.
    c = client._flask_app.test_client()
    assert c.get(f"/ext/{SLUG}/ping").get_json()["ok"] is True

    # Gated file AI tools bound.
    tools = build_device_tools(client, "dev-1")._tools
    for name in ("list_files", "read_text_file", "delete_file"):
        assert f"{PKG}__{name}" in tools

    # Frontend contributions: the route page + the node-detail.tabs widget.
    env = client.get_contributions_envelope()
    routes = {r["path"]: r for r in env.get("routes", [])}
    assert "/x/explorer" in routes and routes["/x/explorer"]["component"] == "ExplorerPage"
    widgets = [w for w in env.get("widgets", []) if w["slot"] == "node-detail.tabs"]
    assert widgets and widgets[0]["component"] == "FilesTab" and widgets[0]["slug"] == SLUG


def test_explorer_file_verbs_require_agent(fresh_db):
    client = _client()
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()

    assert c.get(f"/ext/{SLUG}/devices/dev-1/files?path=/sdcard").status_code == 503
    assert c.delete(f"/ext/{SLUG}/devices/dev-1/files", json={"path": "/sdcard/x"}).status_code == 503
    assert c.post(f"/ext/{SLUG}/devices/dev-1/files/mkdir", json={"path": "/sdcard/y"}).status_code == 503
    assert c.post(f"/ext/{SLUG}/devices/dev-1/files/rename", json={"from": "/a", "to": "/b"}).status_code == 503
    assert c.get(f"/ext/{SLUG}/devices/dev-1/files/preview?path=/sdcard/x").status_code == 503


def test_explorer_validation_errors(fresh_db):
    client = _client()
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()
    # Missing required fields → 400 (before the agent lookup).
    assert c.delete(f"/ext/{SLUG}/devices/dev-1/files", json={}).status_code == 400
    assert c.post(f"/ext/{SLUG}/devices/dev-1/files/rename", json={"from": "/a"}).status_code == 400


def test_explorer_disable_returns_503(fresh_db):
    client = _client()
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()
    assert c.get(f"/ext/{SLUG}/ping").status_code == 200
    client.disable_extension(SLUG)
    assert c.get(f"/ext/{SLUG}/ping").status_code == 503
