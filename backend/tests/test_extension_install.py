"""Extension platform: manifest validation, zip-slip defense, and the install pipeline —
install, hot-load, status guard (503 when disabled), restart survival via the boot loader,
sha256 pinning, and keep-vs-purge uninstall (plan 03 phase 1)."""
import io
import os
import json
import zipfile

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.extension_manifest import (
    validate_manifest, safe_extract_path, ManifestError,
)


class _ExtClient(ExtensionsMixin):
    """Minimal composition exercising the extension mixin without a full Client."""


def _make_zip(slug="demo-ext", version="1.0.0", extra_files=None, manifest_over=None):
    manifest = {
        "name": slug,
        "display_name": "Demo Extension",
        "version": version,
        "category": "utility",
        "permissions": ["network"],
        "entry_point": "routes:bp",
        "url_prefix": f"/extensions/{slug}",
        "lifecycle": {"install": "lifecycle:on_install", "uninstall": "lifecycle:on_uninstall"},
    }
    manifest.update(manifest_over or {})
    routes_py = (
        "from flask import Blueprint, jsonify\n"
        f"bp = Blueprint('{slug.replace('-', '_')}', __name__)\n"
        "@bp.route('/ping')\n"
        "def ping():\n"
        "    return jsonify({'pong': True})\n"
    )
    lifecycle_py = (
        "def on_install(client):\n"
        "    client._hook_installed = True\n"
        "def on_uninstall(client, purge=False):\n"
        "    client._hook_purged = purge\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", routes_py)
        zf.writestr("backend/lifecycle.py", lifecycle_py)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clean_extracted():
    """Remove any extension dirs an install created under devicekit/extensions/."""
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    import shutil
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name == "__init__.py":
            continue
        shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)


def _client_with_app(fresh_db):
    client = _ExtClient()
    client.init_extensions()
    app = Flask(__name__)
    client._flask_app = app
    return client, app


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------
def test_validate_manifest_happy():
    assert validate_manifest({
        "name": "good-ext", "display_name": "Good", "version": "1.2.3",
        "category": "automation", "permissions": ["adb", "llm"],
        "entry_point": "routes:bp",
    }) is True


@pytest.mark.parametrize("manifest,needle", [
    ({"display_name": "x", "version": "1.0.0"}, "missing required"),
    ({"name": "Bad Slug!", "display_name": "x", "version": "1.0.0"}, "alphanumeric"),
    ({"name": "e", "display_name": "x", "version": "notsemver"}, "semver"),
    ({"name": "e", "display_name": "x", "version": "1.0.0", "category": "nope"}, "category"),
    ({"name": "e", "display_name": "x", "version": "1.0.0", "permissions": ["wat"]}, "unknown permissions"),
    ({"name": "e", "display_name": "x", "version": "1.0.0", "entry_point": "notaref"}, "module:attr"),
])
def test_validate_manifest_rejections(manifest, needle):
    with pytest.raises(ManifestError) as ei:
        validate_manifest(manifest)
    assert needle in str(ei.value)


# ---------------------------------------------------------------------------
# Zip-Slip defense
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("evil", ["../escape.py", "sub/../../x.py", "C:/win.py", ""])
def test_safe_extract_path_rejects(tmp_path, evil):
    with pytest.raises(ValueError):
        safe_extract_path(str(tmp_path), evil)


def test_safe_extract_path_allows_normal(tmp_path):
    out = safe_extract_path(str(tmp_path), "pkg/module.py")
    assert out.startswith(str(tmp_path))
    # A leading-slash path is normalized to relative (lstrip), staying inside dest.
    assert safe_extract_path(str(tmp_path), "/abs/path.py").startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# Install pipeline + hot-load + status guard
# ---------------------------------------------------------------------------
def test_install_hotload_and_status_guard(fresh_db):
    client, app = _client_with_app(fresh_db)
    ext = client.install_extension_from_zip(_make_zip())
    assert ext["status"] == "active"
    assert client._hook_installed is True  # lifecycle install hook ran

    c = app.test_client()
    assert c.get("/extensions/demo-ext/ping").get_json() == {"pong": True}

    # disable -> 503 without restart
    client.disable_extension("demo-ext")
    assert c.get("/extensions/demo-ext/ping").status_code == 503
    # enable -> 200
    client.enable_extension("demo-ext")
    assert c.get("/extensions/demo-ext/ping").status_code == 200


def test_preview_pins_sha256_and_install_verifies(fresh_db):
    client, app = _client_with_app(fresh_db)
    zip_bytes = _make_zip()
    preview = client.preview_extension(zip_bytes=zip_bytes)
    assert preview["slug"] == "demo-ext"
    assert len(preview["sha256"]) == 64
    assert preview["permissions"] == ["network"]

    # Correct checksum installs; wrong checksum is a hard failure.
    import hashlib
    good = hashlib.sha256(zip_bytes).hexdigest()

    class _URLClient(_ExtClient):
        def _download_zip(self, url):
            return zip_bytes

    uc = _URLClient()
    uc.init_extensions()
    uc._flask_app = app
    with pytest.raises(ValueError):
        uc.install_extension_from_url("http://x/demo.zip", expected_sha256="00" * 32)
    ext = uc.install_extension_from_url("http://x/demo.zip", expected_sha256=good)
    assert ext["status"] == "active"


def test_already_installed_requires_force(fresh_db):
    client, app = _client_with_app(fresh_db)
    client.install_extension_from_zip(_make_zip())
    with pytest.raises(ValueError) as ei:
        client.install_extension_from_zip(_make_zip())
    assert "already installed" in str(ei.value)
    # force reinstalls
    assert client.install_extension_from_zip(_make_zip(version="1.1.0"), force=True)["version"] == "1.1.0"


# ---------------------------------------------------------------------------
# Restart survival (boot loader) + self-heal
# ---------------------------------------------------------------------------
def test_extension_survives_restart(fresh_db, restart):
    client, app = _client_with_app(fresh_db)
    client.install_extension_from_zip(_make_zip())
    assert app.test_client().get("/extensions/demo-ext/ping").status_code == 200

    restart(fresh_db)  # dispose + re-open same DB file

    client2 = _ExtClient()
    client2.init_extensions()
    app2 = Flask(__name__)
    client2.load_all_extensions(app2)  # boot loader re-activates from DB + on-disk extraction
    assert client2.get_extension("demo-ext")["status"] == "active"
    assert app2.test_client().get("/extensions/demo-ext/ping").status_code == 200


# ---------------------------------------------------------------------------
# Uninstall: keep-data default vs purge (drops ext_<slug>_* tables)
# ---------------------------------------------------------------------------
def test_uninstall_keep_vs_purge(fresh_db):
    from sqlalchemy import text, inspect
    from devicekit.db import get_engine

    client, app = _client_with_app(fresh_db)
    client.install_extension_from_zip(_make_zip())

    # Simulate an extension-owned data table.
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE ext_demo_ext_data (id INTEGER PRIMARY KEY)'))
    assert "ext_demo_ext_data" in inspect(eng).get_table_names()

    # keep-data uninstall leaves the table.
    assert client.uninstall_extension("demo-ext", purge=False) is True
    assert client._hook_purged is False
    assert "ext_demo_ext_data" in inspect(eng).get_table_names()
    assert client.get_extension("demo-ext") is None

    # reinstall then purge drops exactly that prefix.
    client.install_extension_from_zip(_make_zip())
    assert client.uninstall_extension("demo-ext", purge=True) is True
    assert client._hook_purged is True
    assert "ext_demo_ext_data" not in inspect(eng).get_table_names()
