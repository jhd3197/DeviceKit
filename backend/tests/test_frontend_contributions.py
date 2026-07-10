"""Frontend contribution envelope (plan 04): the backend merges every **active**
extension's manifest ``contributions`` block into one envelope the React app renders, and
exposes the frontend-SDK contract version. Disabling an extension drops its contributions
from the envelope without a restart; the JS SDK's ``SDK_VERSION`` must equal the backend
constant so extensions and host agree on the shared surface.
"""
import io
import os
import re
import json
import zipfile

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, SDK_VERSION, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    pass


_ROUTES_PY = (
    "from flask import Blueprint, jsonify\n"
    "bp = Blueprint('demo', __name__)\n"
    "@bp.route('/ping')\n"
    "def ping():\n"
    "    return jsonify({'ok': True})\n"
)

_CONTRIBUTIONS = {
    "nav": [{"id": "demo", "label": "Demo", "route": "/x/demo", "section": "Extensions"}],
    "routes": [{"path": "/x/demo", "component": "DemoPage"}],
    "widgets": [{"slot": "dashboard.top", "component": "DemoWidget"}],
    "page_titles": {"/x/demo": "Demo Page"},
}


def _zip():
    manifest = {
        "name": "demo", "display_name": "Demo", "version": "1.0.0",
        "category": "utility", "entry_point": "routes:bp",
        "url_prefix": "/extensions/demo", "contributions": _CONTRIBUTIONS,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.json", json.dumps(manifest))
        zf.writestr("backend/routes.py", _ROUTES_PY)
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


def _client(fresh_db):
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def test_envelope_merges_active_extension(fresh_db):
    client = _client(fresh_db)
    client.install_extension_from_zip(_zip())

    env = client.get_contributions_envelope()
    assert env["sdk_version"] == SDK_VERSION
    assert env["nav"] == [{"id": "demo", "label": "Demo", "route": "/x/demo",
                           "section": "Extensions", "slug": "demo"}]
    assert env["routes"][0] == {"path": "/x/demo", "component": "DemoPage", "slug": "demo"}
    assert env["widgets"][0] == {"slot": "dashboard.top", "component": "DemoWidget",
                                 "slug": "demo"}
    assert env["page_titles"] == {"/x/demo": "Demo Page"}


def test_disabled_extension_drops_from_envelope(fresh_db):
    client = _client(fresh_db)
    client.install_extension_from_zip(_zip())
    assert client.get_contributions_envelope()["nav"]

    client.disable_extension("demo")
    env = client.get_contributions_envelope()
    assert env["nav"] == []
    assert env["routes"] == []
    assert env["widgets"] == []
    assert env["page_titles"] == {}

    client.enable_extension("demo")
    assert client.get_contributions_envelope()["nav"]


def test_sdk_version_matches_frontend_constant():
    """The JS SDK surface must pin the same version as the backend constant so an extension
    built against ``devicekit-sdk`` and the host agree on the contract."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sdk_index = os.path.join(repo_root, "frontend", "src", "extensions", "sdk", "index.js")
    assert os.path.isfile(sdk_index), f"SDK index missing at {sdk_index}"
    src = open(sdk_index, "r", encoding="utf-8").read()
    m = re.search(r"SDK_VERSION\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "SDK_VERSION constant not found in frontend SDK index"
    assert m.group(1) == SDK_VERSION
