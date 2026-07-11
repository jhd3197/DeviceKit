"""The ``automation_templates`` manifest seam (plan 15 phase 1).

Activating an extension that ships ``automation_templates`` seeds ready-made automations,
tagged ``ext:<slug>`` for provenance. Seeding is idempotent (safe on every boot / enable),
and uninstall removes exactly those seeded automations — the marketplace round-trips clean.
"""
import json
import os
import shutil

import pytest
from flask import Flask

import devicekit.mixins.extensions as ext_mod
from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin

SLUG = "devicekit-tmpl-test"
PKG = SLUG.replace("-", "_")
TAG = f"ext:{SLUG}"


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    def broadcast(self, *a, **k):  # EventsMixin stand-in
        pass


def _write_ext(root):
    base = os.path.join(root, SLUG)
    os.makedirs(os.path.join(base, "backend", "automations"))
    manifest = {
        "name": SLUG, "display_name": "Tmpl Test", "version": "1.0.0",
        "category": "utility", "automation_templates": ["automations/greet.json"],
    }
    with open(os.path.join(base, "extension.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    open(os.path.join(base, "backend", "__init__.py"), "w").close()
    with open(os.path.join(base, "backend", "automations", "greet.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "name": "Greet", "description": "say hi",
            "steps": [{"type": "noop", "config": {}}], "tags": ["demo"],
        }, fh)
    return base


@pytest.fixture
def builtin_root(tmp_path, monkeypatch):
    root = tmp_path / "builtins"
    root.mkdir()
    _write_ext(str(root))
    monkeypatch.setattr(ext_mod, "BUILTIN_EXTENSIONS_DIR", str(root))
    yield str(root)
    shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, PKG), ignore_errors=True)


def _client():
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def _seeded(client):
    return [a for a in client.list_automations() if TAG in (a.get("tags") or [])]


def test_templates_seeded_on_install(fresh_db, builtin_root):
    client = _client()
    client.install_builtin_extension(SLUG)
    autos = _seeded(client)
    assert len(autos) == 1
    a = autos[0]
    assert a["name"] == "Greet"
    assert a["description"] == "say hi"
    assert "demo" in a["tags"] and TAG in a["tags"]
    assert a["steps"] == [{"type": "noop", "config": {}}]


def test_templates_idempotent_on_reactivate(fresh_db, builtin_root):
    client = _client()
    client.install_builtin_extension(SLUG)
    # Re-run activation the way the boot loader / enable does — must not duplicate.
    manifest = client.get_extension(SLUG)["manifest"]
    client._register_contributions(SLUG, manifest)
    client._register_contributions(SLUG, manifest)
    assert len(_seeded(client)) == 1


def test_templates_removed_on_uninstall(fresh_db, builtin_root):
    client = _client()
    client.install_builtin_extension(SLUG)
    assert _seeded(client)
    client.uninstall_extension(SLUG)
    assert not _seeded(client)


def test_templates_survive_disable(fresh_db, builtin_root):
    """Disable is not uninstall — seeded automations persist (only their step types unwire)."""
    client = _client()
    client.install_builtin_extension(SLUG)
    client.disable_extension(SLUG)
    assert len(_seeded(client)) == 1
