"""Extension→extension dependencies (plan 17).

Phase 1: the ``requires_extensions`` manifest key is validated, and install refuses when a
required sibling is absent or version-incompatible — the same gate shape as
``assert_devicekit_compatible``, one level down.

Phase 2: ``sdk.extension(slug)`` dispatches to a sibling's registered ``provides`` surface
in-process, gated on the sibling being *active* (``ExtensionUnavailable`` otherwise), and the
lifecycle graph blocks uninstalling a depended-on extension while an active dependent needs it.
"""
import io
import json
import zipfile

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR  # noqa: F401
from devicekit.extension_manifest import validate_manifest, range_satisfies, ManifestError


class _ExtClient(ExtensionsMixin):
    """Minimal composite exercising the extension mixin without a full Client."""


def _provider_zip(slug="dep-ext", version="1.0.0", manifest_over=None):
    """A provider extension that exposes a sibling-callable ``echo``/``add`` via ``provides``."""
    manifest = {
        "name": slug,
        "display_name": "Dependency Extension",
        "version": version,
        "category": "utility",
        "permissions": ["network"],
        "entry_point": "routes:bp",
        "provides": "api:register",
    }
    manifest.update(manifest_over or {})
    routes_py = (
        "from flask import Blueprint, jsonify\n"
        f"bp = Blueprint('{slug.replace('-', '_')}', __name__)\n"
        "@bp.route('/ping')\n"
        "def ping():\n"
        "    return jsonify({'pong': True})\n"
    )
    api_py = (
        "def echo(text):\n"
        "    return {'echoed': text}\n"
        "def add(a, b=0):\n"
        "    return a + b\n"
        "def register(api):\n"
        "    api.method(echo)\n"
        "    api.method(add)\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", routes_py)
        zf.writestr("backend/api.py", api_py)
    return buf.getvalue()


def _consumer_zip(slug="consumer-ext", requires=None, version="1.0.0"):
    """A consumer extension that declares ``requires_extensions`` and calls the sibling."""
    manifest = {
        "name": slug,
        "display_name": "Consumer Extension",
        "version": version,
        "category": "utility",
        "permissions": ["network"],
        "entry_point": "routes:bp",
        "requires_extensions": requires if requires is not None else {"dep-ext": ">=1.0.0"},
    }
    routes_py = (
        "from flask import Blueprint, jsonify\n"
        "import devicekit_sdk\n"
        f"bp = Blueprint('{slug.replace('-', '_')}', __name__)\n"
        "@bp.route('/call')\n"
        "def call():\n"
        "    dep = devicekit_sdk.extension('dep-ext')\n"
        "    return jsonify(dep.echo('hi'))\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", routes_py)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clean_extracted():
    import os
    import shutil
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)


def _client():
    client = _ExtClient()
    client.init_extensions()
    client._flask_app = Flask(__name__)
    return client


# ---------------------------------------------------------------------------
# Manifest validation + range matcher
# ---------------------------------------------------------------------------
def test_validate_requires_extensions_happy():
    assert validate_manifest({
        "name": "c", "display_name": "C", "version": "1.0.0",
        "requires_extensions": {"devicekit-browser": ">=0.1.0"},
    }) is True
    # Absent map is unchanged behaviour.
    assert validate_manifest({"name": "c", "display_name": "C", "version": "1.0.0"}) is True


@pytest.mark.parametrize("requires,needle", [
    ("devicekit-browser", "must be an object"),
    ({"Bad Slug!": ">=1.0.0"}, "not a valid slug"),
    ({"devicekit-browser": 5}, "version range string"),
])
def test_validate_requires_extensions_rejections(requires, needle):
    with pytest.raises(ManifestError) as ei:
        validate_manifest({
            "name": "c", "display_name": "C", "version": "1.0.0",
            "requires_extensions": requires,
        })
    assert needle in str(ei.value)


@pytest.mark.parametrize("current,spec,ok", [
    ("1.0.0", ">=0.1.0", True),
    ("1.0.0", ">=1.0.0", True),
    ("1.0.0", ">1.0.0", False),
    ("1.0.0", "<2.0.0", True),
    ("2.0.0", "<2.0.0", False),
    ("1.5.0", ">=1.0 <2.0", True),
    ("2.5.0", ">=1.0 <2.0", False),
    ("1.2.3", "*", True),
    ("1.2.3", "", True),
    ("1.2.3", None, True),
    ("1.2.0", "==1.2.0", True),
    ("1.2.1", "==1.2.0", False),
])
def test_range_satisfies(current, spec, ok):
    assert range_satisfies(current, spec) is ok


# ---------------------------------------------------------------------------
# Install-time enforcement
# ---------------------------------------------------------------------------
def test_install_refuses_when_dependency_missing(fresh_db):
    client = _client()
    with pytest.raises(ValueError) as ei:
        client.install_extension_from_zip(_consumer_zip())
    assert "dep-ext" in str(ei.value) and "not installed" in str(ei.value)
    # Nothing was persisted for the consumer.
    assert client.get_extension("consumer-ext") is None


def test_install_succeeds_when_dependency_present(fresh_db):
    client = _client()
    client.install_extension_from_zip(_provider_zip())
    ext = client.install_extension_from_zip(_consumer_zip())
    assert ext["status"] == "active"


def test_install_refuses_on_version_mismatch(fresh_db):
    client = _client()
    client.install_extension_from_zip(_provider_zip(version="1.0.0"))
    with pytest.raises(ValueError) as ei:
        client.install_extension_from_zip(_consumer_zip(requires={"dep-ext": ">=2.0.0"}))
    assert "v1.0.0 is installed" in str(ei.value)


def test_preview_surfaces_missing_dependency(fresh_db):
    client = _client()
    preview = client.preview_extension(zip_bytes=_consumer_zip())
    assert preview["requires_extensions"] == {"dep-ext": ">=1.0.0"}
    assert any("not installed" in w and "dep-ext" in w for w in preview["warnings"])
