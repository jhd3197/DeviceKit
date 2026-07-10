"""The reference builtin (``devicekit-webhook-notify``) proves the platform end-to-end:
installs from ``builtin-extensions/`` and from the (bundled) registry, contributes a step
type + AI tool + blueprint + an ``ext_*`` table, masks its secret config, survives a
restart, returns 503 when disabled, and purges its table on uninstall (plan 03 phase 4)."""
import os
import shutil

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools

SLUG = "devicekit-webhook-notify"
PKG = SLUG.replace("-", "_")


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    def broadcast(self, *a, **k):  # EventsMixin stand-in for the notify helper
        pass


@pytest.fixture(autouse=True)
def _clean():
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()


def _client(fresh_db):
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def test_builtin_installs_and_contributes(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client(fresh_db)
    ext = client.install_builtin_extension(SLUG)
    assert ext["status"] == "active" and ext["source"] == "builtin"

    # Step type appears in the AutomationEditor registry (JSON-safe, execute stripped).
    st = client.get_step_types()
    assert "notify.webhook" in st and "execute" not in st["notify.webhook"]

    # AI tool bound namespaced.
    assert f"{PKG}__send_notification" in build_device_tools(client, "d")._tools

    # Blueprint serves (status guard passes while active).
    c = client._flask_app.test_client()
    body = c.get(f"/extensions/{SLUG}/ping").get_json()
    assert body["ok"] is True and body["configured"] is False

    # ext_<slug>_* table created.
    assert "ext_devicekit_webhook_notify_deliveries" in inspect(get_engine()).get_table_names()


def test_builtin_secret_config_masked(fresh_db):
    client = _client(fresh_db)
    client.install_builtin_extension(SLUG)
    client.update_extension_config(SLUG, {"webhook_url": "https://hooks.example/abc", "default_message": "hi"})

    cfg = client.get_extension_config(SLUG)
    assert cfg["webhook_url"] == "••••••"        # secret masked in API view
    assert cfg["default_message"] == "hi"        # non-secret visible

    # ...but the extension's in-process SDK view sees the real value.
    import devicekit_sdk
    assert devicekit_sdk.config(SLUG)["webhook_url"] == "https://hooks.example/abc"


def test_builtin_disable_returns_503(fresh_db):
    client = _client(fresh_db)
    client.install_builtin_extension(SLUG)
    c = client._flask_app.test_client()
    assert c.get(f"/extensions/{SLUG}/ping").status_code == 200
    client.disable_extension(SLUG)
    assert c.get(f"/extensions/{SLUG}/ping").status_code == 503
    assert "notify.webhook" not in client.get_step_types()


def test_builtin_survives_restart(fresh_db, restart):
    client = _client(fresh_db)
    client.install_builtin_extension(SLUG)
    restart(fresh_db)
    client2 = _ExtClient()
    client2.init_extensions()
    client2.load_all_extensions(Flask(__name__))
    assert client2.get_extension(SLUG)["status"] == "active"
    assert client2._flask_app.test_client().get(f"/extensions/{SLUG}/ping").status_code == 200


def test_builtin_via_registry_bundled(fresh_db, monkeypatch):
    # Disabled registry (set-but-empty) ⇒ bundled index, which lists the builtin as bundled.
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "")
    from devicekit import extension_registry
    extension_registry._reset_cache()
    client = _client(fresh_db)
    ext = client.install_extension_from_registry(SLUG)
    assert ext["status"] == "active"
    assert "notify.webhook" in client.get_step_types()


def test_builtin_uninstall_purge(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client(fresh_db)
    client.install_builtin_extension(SLUG)
    assert "ext_devicekit_webhook_notify_deliveries" in inspect(get_engine()).get_table_names()
    client.uninstall_extension(SLUG, purge=True)
    assert "ext_devicekit_webhook_notify_deliveries" not in inspect(get_engine()).get_table_names()
