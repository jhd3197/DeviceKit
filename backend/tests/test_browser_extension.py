"""devicekit-browser (plan 15 phase 2): the CDP driver installs and contributes a device
API, pool routing, gated AI tools, browser step types, its own tables, and a seeded
automation — all without a physical device. Pool dispatch (round-robin membership + cursor)
is exercised with stub devices; live Chrome driving needs a phone (verified separately).
"""
import os
import shutil

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools

SLUG = "devicekit-browser"
PKG = SLUG.replace("-", "_")


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    _fake_devices = []

    def broadcast(self, *a, **k):
        pass

    def get_devices(self):
        return list(self._fake_devices)

    def get_device(self, device_id):
        for d in self._fake_devices:
            if d.get("device_id") == device_id or d.get("serial") == device_id:
                return d
        return None


@pytest.fixture(autouse=True)
def _clean():
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()


def _client(fake_devices=None):
    c = _ExtClient()
    c._fake_devices = fake_devices or []
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def test_browser_installs_and_contributes(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client()
    ext = client.install_builtin_extension(SLUG)
    assert ext["status"] == "active" and ext["source"] == "builtin"

    # Step types registered (execute stripped from the JSON-safe view).
    st = client.get_step_types()
    for t in ("browser_goto", "browser_assert_text", "browser_evaluate", "browser_screenshot"):
        assert t in st and "execute" not in st[t]

    # AI tools bound namespaced.
    tools = build_device_tools(client, "dev-1")._tools
    for name in ("goto", "evaluate", "get_content", "get_url", "screenshot", "fetch_url"):
        assert f"{PKG}__{name}" in tools

    # Blueprint mounted at /ext/devicekit-browser.
    c = client._flask_app.test_client()
    body = c.get(f"/ext/{SLUG}/ping").get_json()
    assert body["ok"] is True

    # Tables created.
    names = inspect(get_engine()).get_table_names()
    for suffix in ("sessions", "pools", "sticky"):
        assert f"ext_{PKG}_{suffix}" in names

    # Automation template seeded, tagged with the source slug.
    seeded = [a for a in client.list_automations() if f"ext:{SLUG}" in (a.get("tags") or [])]
    assert len(seeded) == 1
    assert seeded[0]["steps"][0]["type"] == "browser_goto"


def test_browser_pool_crud_via_blueprint(fresh_db):
    devs = [{"device_id": "A"}, {"device_id": "B"}]
    client = _client(devs)
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()

    r = c.post(f"/ext/{SLUG}/pools", json={"name": "farm", "all": True, "strategy": "round_robin"})
    assert r.status_code == 201
    assert r.get_json()["name"] == "farm"

    listed = c.get(f"/ext/{SLUG}/pools").get_json()
    assert listed["count"] == 1 and listed["pools"][0]["name"] == "farm"

    status = c.get(f"/ext/{SLUG}/pools/farm/status").get_json()
    assert set(status["rotation"]) == {"A", "B"}
    assert status["strategy"] == "round_robin"


def test_browser_pool_round_robin_dispatch(fresh_db):
    devs = [{"device_id": d} for d in ("A", "B", "C")]
    client = _client(devs)
    client.install_builtin_extension(SLUG)
    import devicekit_sdk
    devicekit_sdk.set_host(client)  # ensure the module façade points at this client
    from devicekit.extensions.devicekit_browser import pools

    pools.create_pool("rr", {"devices": ["A", "B", "C"]}, "round_robin")
    pool = pools.get_pool("rr")
    picks = [pools.pick_device(pools.get_pool("rr")) for _ in range(4)]
    assert picks == ["A", "B", "C", "A"]  # cursor rotates and persists


def test_browser_device_not_connected_errors(fresh_db):
    client = _client([])  # no devices connected
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()
    r = c.post(f"/ext/{SLUG}/devices/ghost/goto", json={"url": "https://example.com"})
    assert r.status_code == 502
    assert "not connected" in r.get_json()["error"].lower()


def test_browser_disable_returns_503(fresh_db):
    client = _client()
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()
    assert c.get(f"/ext/{SLUG}/ping").status_code == 200
    client.disable_extension(SLUG)
    assert c.get(f"/ext/{SLUG}/ping").status_code == 503
    assert "browser_goto" not in client.get_step_types()


def test_browser_uninstall_purges(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client()
    client.install_builtin_extension(SLUG)
    assert f"ext_{PKG}_pools" in inspect(get_engine()).get_table_names()
    client.uninstall_extension(SLUG, purge=True)
    names = inspect(get_engine()).get_table_names()
    assert f"ext_{PKG}_pools" not in names
    # Seeded automation removed on uninstall.
    assert not [a for a in client.list_automations() if f"ext:{SLUG}" in (a.get("tags") or [])]
