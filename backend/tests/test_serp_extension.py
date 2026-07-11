"""devicekit-serp (plan 17 phase 3): the dependency mechanism proven end-to-end on a real
consumer. SERP owns no device code — it install-depends on devicekit-browser and reaches it via
``sdk.extension("devicekit-browser").fetch``. Here the browser's provided ``fetch`` is stubbed
with canned engine HTML, so parsing + the search flow + the step type run without a phone (live
Chrome scraping is verified separately on hardware).
"""
import os
import shutil

import pytest
from flask import Flask

import devicekit_sdk
from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.prompture_agent import build_device_tools

BROWSER = "devicekit-browser"
SERP = "devicekit-serp"


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin):
    def broadcast(self, *a, **k):
        pass

    def get_devices(self):
        return []

    def get_device(self, device_id):
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


def _client():
    c = _ExtClient()
    c.init_extensions()
    c._flask_app = Flask(__name__)
    devicekit_sdk.set_host(c)
    return c


def _install_pair(client):
    client.install_builtin_extension(BROWSER)
    client.install_builtin_extension(SERP)


def _stub_fetch(client, html, device_id="dev-stub"):
    """Replace the browser's provided ``fetch`` with a stub returning canned HTML — exercises the
    real sdk.extension dispatch + status gate, just short-circuiting the device round-trip."""
    def fetch(pool="default", url=None, fmt="html"):
        return {"device_id": device_id, "url": url, "html": html}
    client._ext_extension_api[BROWSER]["fetch"] = fetch


# --------------------------------------------------------------------------- canned HTML
GOOGLE_HTML = """
<html><body><div id="search">
  <div class="g"><a href="https://example.com/a"><h3>Example A</h3></a>
     <div class="VwiC3b">Snippet A</div></div>
  <div class="g"><a href="/url?q=https://example.org/b&sa=U"><h3>Example B</h3></a>
     <div class="VwiC3b">Snippet B</div></div>
  <div class="g"><a href="https://accounts.google.com/signin"><h3>Sign in</h3></a></div>
</div></body></html>
"""

BING_HTML = """
<html><body><ol id="b_results">
  <li class="b_algo"><h2><a href="https://example.com/a">Bing A</a></h2>
     <div class="b_caption"><p>Cap A</p></div></li>
  <li class="b_algo"><h2><a href="https://example.org/b">Bing B</a></h2>
     <div class="b_caption"><p>Cap B</p></div></li>
</ol></body></html>
"""

DDG_HTML = """
<html><body><div class="results">
  <div class="result results_links">
     <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">DDG A</a>
     <a class="result__snippet">Snip A</a></div>
  <div class="result result--ad">
     <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fads.example%2Fx">Ad</a></div>
  <div class="result">
     <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fb">DDG B</a></div>
</div></body></html>
"""


# --------------------------------------------------------------------------- install / deps
def test_serp_requires_browser(fresh_db):
    client = _client()
    with pytest.raises(ValueError) as ei:
        client.install_builtin_extension(SERP)
    assert BROWSER in str(ei.value) and "not installed" in str(ei.value)


def test_serp_installs_after_browser_and_contributes(fresh_db):
    client = _client()
    _install_pair(client)
    assert client.get_extension(SERP)["status"] == "active"

    # Step type registered (execute stripped from the JSON-safe view).
    st = client.get_step_types()
    assert "serp_search" in st and "execute" not in st["serp_search"]
    assert st["serp_search"]["config"]["engine"]["options"] == ["google", "bing", "duckduckgo"]

    # AI tool bound, namespaced + read-only (fleet-level — no device_id param).
    tools = build_device_tools(client, "dev-1")._tools
    assert "devicekit_serp__search" in tools

    # The headline demo automation is seeded, tagged by provenance, and chains serp -> browser.
    seeded = [a for a in client.list_automations() if f"ext:{SERP}" in (a.get("tags") or [])]
    assert len(seeded) == 1
    types = [s["type"] for s in seeded[0]["steps"]]
    assert types == ["serp_search", "browser_goto", "browser_screenshot"]
    assert seeded[0]["steps"][1]["config"]["url"] == "{{serp_top_url}}"


# --------------------------------------------------------------------------- engine parsing
def test_serp_search_parses_google(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, GOOGLE_HTML, device_id="samsung")
    from devicekit.extensions.devicekit_serp import search as serp

    res = serp.search("example", engine="google", count=10, pool="default")
    assert res["engine"] == "google" and res["device_id"] == "samsung"
    urls = [r["url"] for r in res["results"]]
    assert urls == ["https://example.com/a", "https://example.org/b"]  # accounts.google filtered
    assert res["results"][0]["title"] == "Example A"
    assert res["results"][0]["snippet"] == "Snippet A"


def test_serp_search_parses_bing(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, BING_HTML)
    from devicekit.extensions.devicekit_serp import search as serp

    res = serp.search("example", engine="bing")
    assert [r["url"] for r in res["results"]] == ["https://example.com/a", "https://example.org/b"]
    assert res["results"][0]["title"] == "Bing A" and res["results"][0]["snippet"] == "Cap A"


def test_serp_search_parses_duckduckgo(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, DDG_HTML)
    from devicekit.extensions.devicekit_serp import search as serp

    res = serp.search("example", engine="duckduckgo")
    # uddg redirect decoded, the ad result skipped.
    assert [r["url"] for r in res["results"]] == ["https://example.com/a", "https://example.org/b"]


def test_serp_count_limits_results(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, GOOGLE_HTML)
    from devicekit.extensions.devicekit_serp import search as serp

    assert len(serp.search("example", engine="google", count=1)["results"]) == 1


def test_serp_unknown_engine_raises(fresh_db):
    client = _client()
    _install_pair(client)
    from devicekit.extensions.devicekit_serp import search as serp

    with pytest.raises(ValueError):
        serp.search("example", engine="altavista")


# --------------------------------------------------------------------------- resilience
def test_serp_parse_failure_is_explicit(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, "<html><body><p>no results container here</p></body></html>")
    from devicekit.extensions.devicekit_serp import search as serp

    res = serp.search("example", engine="google")
    assert res["results"] == [] and res["count"] == 0
    assert "could not parse" in res["error"]           # explicit, not silent empty
    assert res["html_sample"]                           # raw HTML retained for debugging


def test_serp_unavailable_when_browser_disabled(fresh_db):
    client = _client()
    _install_pair(client)
    client.disable_extension(BROWSER)
    from devicekit.extensions.devicekit_serp import search as serp

    with pytest.raises(devicekit_sdk.ExtensionUnavailable):
        serp.search("example", engine="google")


# --------------------------------------------------------------------------- step type + chaining
def test_serp_step_stores_structured_variable(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, GOOGLE_HTML)

    variables = {}
    step = {"type": "serp_search",
            "config": {"query": "example", "engine": "google", "store_as": "serp"}}
    out = client._execute_step(step, "dev-1", variables=variables)
    client._store_step_var(variables, step, out)

    # The "open first result" primitive + a couple of flattened scalars.
    assert variables["serp_top_url"] == "https://example.com/a"
    assert variables["serp_device_id"] == "dev-stub"
    assert '"results"' in variables["serp"]             # full payload as JSON under {{serp}}


def test_serp_step_parse_failure_fails_step(fresh_db):
    client = _client()
    _install_pair(client)
    _stub_fetch(client, "<html><body><p>blocked</p></body></html>")
    step = {"type": "serp_search", "config": {"query": "example"}}
    with pytest.raises(Exception) as ei:
        client._execute_step(step, "dev-1")
    assert "could not parse" in str(ei.value)


# --------------------------------------------------------------------------- registry chain (ph4)
@pytest.fixture
def _bundled_registry(monkeypatch):
    # set-but-empty ⇒ bundled index only (offline, deterministic).
    monkeypatch.setenv("DEVICEKIT_REGISTRY_URL", "")
    from devicekit import extension_registry
    extension_registry._reset_cache()
    yield
    extension_registry._reset_cache()


def test_registry_entry_exposes_requires(_bundled_registry):
    from devicekit import extension_registry
    assert extension_registry.get_entry(SERP)["requires"] == {"devicekit-browser": ">=0.1.0"}
    # An extension with no deps normalizes to an empty map (not missing).
    assert extension_registry.get_entry(BROWSER)["requires"] == {}


def test_serp_installs_from_registry_with_chain(fresh_db, _bundled_registry):
    client = _client()
    # Installing serp from the registry pulls in its dependency (devicekit-browser) first.
    ext = client.install_extension_from_registry(SERP)
    assert ext["status"] == "active"
    assert client.get_extension(BROWSER)["status"] == "active"  # chain installed the dependency


def test_serp_registry_install_without_chain_is_gated(fresh_db, _bundled_registry):
    client = _client()
    # Opting out of the chain leaves the dependency unmet, so the install gate refuses.
    with pytest.raises(ValueError) as ei:
        client.install_extension_from_registry(SERP, install_deps=False)
    assert BROWSER in str(ei.value)


# --------------------------------------------------------------------------- lifecycle graph
def test_browser_uninstall_blocked_while_serp_active(fresh_db):
    client = _client()
    _install_pair(client)
    with pytest.raises(ValueError) as ei:
        client.uninstall_extension(BROWSER)
    assert SERP in str(ei.value)
    # Uninstalling the dependent first frees the dependency.
    assert client.uninstall_extension(SERP) is True
    assert client.uninstall_extension(BROWSER) is True
