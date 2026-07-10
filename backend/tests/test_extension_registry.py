"""Extension registry (plan 03 phase 3): TTL cache, the offline fallback chain
(remote -> last-good cache -> bundled), env-var semantics, update checks, and
install-from-registry with checksum pinning."""
import io
import json
import zipfile

import pytest
from flask import Flask

from devicekit import extension_registry as reg
from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR


class _ExtClient(ExtensionsMixin):
    pass


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    reg._reset_cache()
    monkeypatch.delenv("DEVICEKIT_REGISTRY_URL", raising=False)
    monkeypatch.delenv("DEVICEKIT_REGISTRY_TTL", raising=False)
    yield
    reg._reset_cache()
    import os, shutil
    if os.path.isdir(_EXTENSIONS_PKG_DIR):
        for name in os.listdir(_EXTENSIONS_PKG_DIR):
            if name != "__init__.py":
                shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)


def _remote(entries):
    return lambda url: [reg._normalize(e) for e in entries]


# ---------------------------------------------------------------------------
# Env-var semantics + fallback chain
# ---------------------------------------------------------------------------
def test_disabled_uses_bundled(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "")   # set-but-empty ⇒ disabled
    assert reg.get_registry_url() is None
    entries = reg.list_extensions()
    slugs = {e["slug"] for e in entries}
    assert "devicekit-visual-regression" in slugs   # from the bundled copy
    assert reg.source_label() == "bundled"


def test_unset_uses_default_url(monkeypatch):
    assert reg.get_registry_url() == reg.DEFAULT_REGISTRY_URL


def test_remote_then_cache(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")
    calls = {"n": 0}

    def fake(url):
        calls["n"] += 1
        return [reg._normalize({"slug": "a", "display_name": "A", "version": "1.0.0"})]

    monkeypatch.setattr(reg, "_fetch_remote", fake)
    assert reg.list_extensions()[0]["slug"] == "a"
    assert reg.source_label() == "remote"
    reg.list_extensions()          # within TTL ⇒ served from cache
    assert calls["n"] == 1


def test_remote_failure_keeps_last_good(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")
    monkeypatch.setattr(reg, "_fetch_remote", _remote([{"slug": "a", "display_name": "A", "version": "1.0.0"}]))
    assert reg.list_extensions(force=True)[0]["slug"] == "a"

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(reg, "_fetch_remote", boom)
    entries = reg.list_extensions(force=True)   # force refresh, but remote fails
    assert entries[0]["slug"] == "a"            # last-good cache retained
    assert reg.source_label() == "cache"


def test_remote_failure_no_cache_falls_back_to_bundled(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(reg, "_fetch_remote", boom)
    entries = reg.list_extensions(force=True)
    assert reg.source_label() == "bundled"
    assert any(e["slug"] == "devicekit-visual-regression" for e in entries)


def test_normalize_strips_unknown_fields(monkeypatch):
    e = reg._normalize({"slug": "a", "display_name": "A", "version": "1", "evil": "x"})
    assert "evil" not in e
    assert e["permissions"] == [] and e["bundled"] is False


# ---------------------------------------------------------------------------
# Browse + updates + install-from-registry
# ---------------------------------------------------------------------------
def _install_zip(slug, version):
    manifest = {
        "name": slug, "display_name": slug, "version": version, "category": "utility",
        "entry_point": "routes:bp", "url_prefix": f"/extensions/{slug}",
    }
    routes = "from flask import Blueprint\nbp = Blueprint('%s', __name__)\n" % slug.replace("-", "_")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", routes)
    return buf.getvalue()


def test_registry_browse_enriches_install_state(fresh_db, monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")
    monkeypatch.setattr(reg, "_fetch_remote", _remote([
        {"slug": "cool-ext", "display_name": "Cool", "version": "2.0.0", "source": "http://x/cool.zip"},
    ]))
    client = _ExtClient()
    client.init_extensions()
    client._flask_app = Flask(__name__)
    client.install_extension_from_zip(_install_zip("cool-ext", "1.0.0"))

    catalog = client.get_extension_registry()
    row = next(e for e in catalog["extensions"] if e["slug"] == "cool-ext")
    assert row["installed"] is True and row["installed_version"] == "1.0.0"
    assert row["version"] == "2.0.0"


def test_check_updates_reports_newer(fresh_db, monkeypatch):
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")
    monkeypatch.setattr(reg, "_fetch_remote", _remote([
        {"slug": "cool-ext", "display_name": "Cool", "version": "2.0.0", "source": "http://x/cool.zip"},
    ]))
    client = _ExtClient()
    client.init_extensions()
    client._flask_app = Flask(__name__)
    client.install_extension_from_zip(_install_zip("cool-ext", "1.0.0"))

    updates = client.check_extension_updates()
    assert len(updates) == 1
    assert updates[0]["slug"] == "cool-ext"
    assert updates[0]["available_version"] == "2.0.0" and updates[0]["has_update"] is True


def test_install_from_registry_pins_sha256(fresh_db, monkeypatch):
    import hashlib
    zip_bytes = _install_zip("cool-ext", "1.0.0")
    good = hashlib.sha256(zip_bytes).hexdigest()
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "http://x/index.json")
    monkeypatch.setattr(reg, "_fetch_remote", _remote([
        {"slug": "cool-ext", "display_name": "Cool", "version": "1.0.0",
         "source": "http://x/cool.zip", "sha256": good, "min_devicekit_version": "1.0.0"},
    ]))

    class _URLClient(_ExtClient):
        def _download_zip(self, url):
            return zip_bytes

    client = _URLClient()
    client.init_extensions()
    client._flask_app = Flask(__name__)
    ext = client.install_extension_from_registry("cool-ext")
    assert ext["status"] == "active" and ext["source"] == "registry"

    # A tampered registry checksum is a hard failure.
    reg._reset_cache()
    monkeypatch.setattr(reg, "_fetch_remote", _remote([
        {"slug": "cool-ext", "display_name": "Cool", "version": "1.0.1",
         "source": "http://x/cool.zip", "sha256": "0" * 64, "min_devicekit_version": "1.0.0"},
    ]))
    with pytest.raises(ValueError):
        client.install_extension_from_registry("cool-ext", force=True)
