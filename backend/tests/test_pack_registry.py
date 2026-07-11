"""Plan 15 phase 5: the three pack extensions appear in the bundled registry as first-party
builtins with real (non-placeholder) sha256s, and install through the registry/marketplace
path — not just the direct builtin installer.
"""
import os
import shutil

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.mixins.notifications import NotificationsMixin

PACK = ["devicekit-browser", "devicekit-explorer", "devicekit-notification-capture"]


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin, JobsMixin, NotificationsMixin):
    def __init__(self):
        self._agent_device_states = {}

    def broadcast(self, *a, **k):
        pass

    def get_devices(self):
        return []

    def get_device(self, device_id):
        return None


@pytest.fixture(autouse=True)
def _clean():
    from devicekit.jobs import registry
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()
    registry.clear()


@pytest.fixture(autouse=True)
def _bundled_registry(monkeypatch):
    # set-but-empty ⇒ bundled index only (offline, deterministic)
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "")
    from devicekit import extension_registry
    extension_registry._reset_cache()
    yield
    extension_registry._reset_cache()


def test_pack_entries_are_bundled_with_real_sha256():
    from devicekit import extension_registry
    for slug in PACK:
        entry = extension_registry.get_entry(slug)
        assert entry, f"{slug} missing from bundled registry"
        assert entry["bundled"] is True and entry["first_party"] is True
        sha = entry["sha256"]
        assert sha and set(sha) != {"0"} and len(sha) == 64, f"{slug} needs a real sha256"


@pytest.mark.parametrize("slug", PACK)
def test_pack_installs_from_registry(fresh_db, slug):
    client = _ExtClient()
    client.init_extensions()
    client._flask_app = Flask(__name__)
    ext = client.install_extension_from_registry(slug)
    assert ext["status"] == "active"
    # Its device-scoped blueprint mounts at /ext/<slug>.
    assert client._flask_app.test_client().get(f"/ext/{slug}/ping").status_code == 200
