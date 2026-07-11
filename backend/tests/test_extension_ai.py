"""Per-extension hub keys + the sdk.ai LLM surface (plan 19 phase 4).

Hub admin calls are monkeypatched — these tests prove the lifecycle (issue at install /
reuse / revoke at uninstall), the credential routing per backend, and that the key store
is server-managed and masked.
"""
import pytest

import devicekit_sdk
from devicekit import ai_backend
from devicekit.mixins.extension_ai import ExtensionAiMixin, EXT_HUB_KEYS_SETTING
from devicekit.mixins.settings import SettingsMixin
from devicekit_sdk.permissions import PermissionDenied


class _Client(ExtensionAiMixin, SettingsMixin):
    """Settings + extension-AI, with a stubbed extension registry."""

    def __init__(self, extensions=None):
        self._exts = extensions or {}

    def get_extension(self, slug):
        return self._exts.get(slug)


class _FakeResp:
    def __init__(self, status_code=201, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


LLM_EXT = {
    "slug": "summarizer",
    "status": "active",
    "permissions": ["llm"],
    "manifest": {"name": "summarizer", "permissions": ["llm"],
                 "llm_allowed_models": ["ollama/qwen2.5:1.5b"],
                 "llm_daily_cap_usd": 0.5},
}
NO_LLM_EXT = {
    "slug": "quiet", "status": "active", "permissions": ["adb"],
    "manifest": {"name": "quiet", "permissions": ["adb"]},
}


@pytest.fixture(autouse=True)
def _host_and_registry(monkeypatch):
    """Wire the SDK host to a fresh stub client and restore Prompture built-ins after."""
    yield
    devicekit_sdk.set_host(None)
    from prompture.drivers.provider_descriptors import register_all_builtin_drivers
    register_all_builtin_drivers()


def _hub_client(monkeypatch, extensions=None, admin_token="admt"):
    c = _Client(extensions or {"summarizer": LLM_EXT, "quiet": NO_LLM_EXT})
    devicekit_sdk.set_host(c)
    c.update_settings({"ai.backend": "hub", "ai.hub.key": "ph_host"})
    if admin_token:
        monkeypatch.setenv("HUB_ADMIN_TOKEN", admin_token)
    else:
        monkeypatch.delenv("HUB_ADMIN_TOKEN", raising=False)
    return c


# --------------------------------------------------------------------------- key lifecycle
def test_ensure_creates_scoped_key_from_manifest(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    posted = {}

    def _post(url, headers=None, json=None, timeout=None):
        posted.update({"url": url, "headers": headers, "body": json})
        return _FakeResp(201, {"id": 7, "key": "ph_ext_secret"})
    monkeypatch.setattr(ai_backend.requests, "post", _post)

    record = c.ensure_extension_hub_key("summarizer")
    assert record["id"] == 7
    assert record["key"] == "ph_ext_secret"
    assert posted["url"] == "http://localhost:1984/admin/keys"
    assert posted["headers"] == {"Authorization": "Bearer admt"}
    assert posted["body"]["name"] == "devicekit-ext:summarizer"
    assert posted["body"]["allowed_models"] == ["ollama/qwen2.5:1.5b"]
    assert posted["body"]["daily_spend_cap_usd"] == 0.5

    # Second ensure reuses the stored record — no second admin call.
    monkeypatch.setattr(ai_backend.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-created")))
    assert c.ensure_extension_hub_key("summarizer")["id"] == 7


def test_ensure_noop_on_direct_backend(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    c.update_settings({"ai.backend": "direct"})
    assert c.ensure_extension_hub_key("summarizer") is None


def test_ensure_without_admin_token_returns_none(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch, admin_token=None)
    assert c.ensure_extension_hub_key("summarizer") is None


def test_revoke_removes_record_and_calls_hub(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    monkeypatch.setattr(ai_backend.requests, "post",
                        lambda *a, **k: _FakeResp(201, {"id": 7, "key": "ph_x"}))
    c.ensure_extension_hub_key("summarizer")

    deleted = {}

    def _delete(url, headers=None, timeout=None):
        deleted["url"] = url
        return _FakeResp(204)
    monkeypatch.setattr(ai_backend.requests, "delete", _delete)

    assert c.revoke_extension_hub_key("summarizer") is True
    assert deleted["url"] == "http://localhost:1984/admin/keys/7"
    assert c.get_extension_hub_key("summarizer") is None
    assert c.revoke_extension_hub_key("summarizer") is False  # already gone


# --------------------------------------------------------------------------- call routing
def test_conversation_uses_extension_key_on_hub(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    monkeypatch.setattr(ai_backend.requests, "post",
                        lambda *a, **k: _FakeResp(201, {"id": 1, "key": "ph_ext"}))
    conv = c.extension_ai_conversation("summarizer", model="ollama/qwen2.5:1.5b")
    driver = conv._driver
    assert type(driver).__name__ == "HubDriver"
    assert driver.api_key == "ph_ext"            # the extension's key, NOT ph_host
    assert driver.model == "ollama/qwen2.5:1.5b"


def test_conversation_requires_llm_permission(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    with pytest.raises(PermissionDenied):
        c.extension_ai_conversation("quiet")
    with pytest.raises(PermissionDenied):
        devicekit_sdk.ai("quiet").ask("hello")


def test_sdk_ask_routes_to_host(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    called = {}

    def _ask(slug, prompt, model=None, system_prompt=None):
        called.update({"slug": slug, "prompt": prompt})
        return "hi"
    monkeypatch.setattr(c, "extension_ai_ask", _ask)

    assert devicekit_sdk.ai("summarizer").ask("summarize this") == "hi"
    assert called == {"slug": "summarizer", "prompt": "summarize this"}


def test_direct_backend_falls_back_to_host_credentials(fresh_db, monkeypatch, caplog):
    import logging
    c = _hub_client(monkeypatch)
    c.update_settings({"ai.backend": "direct", "ai.default_model": "openai/gpt-4o"})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-host")
    with caplog.at_level(logging.WARNING, logger="devicekit.mixins.extension_ai"):
        conv = c.extension_ai_conversation("summarizer")
    assert type(conv._driver).__name__ != "HubDriver"
    assert "host provider credentials" in caplog.text


# --------------------------------------------------------------------------- key store safety
def test_extension_keys_masked_and_not_client_writable(fresh_db, monkeypatch):
    c = _hub_client(monkeypatch)
    monkeypatch.setattr(ai_backend.requests, "post",
                        lambda *a, **k: _FakeResp(201, {"id": 1, "key": "ph_ext_secret"}))
    c.ensure_extension_hub_key("summarizer")

    settings = c.get_all_settings()
    assert settings[EXT_HUB_KEYS_SETTING] == {"summarizer": True}
    assert "ph_ext_secret" not in str(settings)

    # A client PUT cannot clobber the server-managed store.
    c.update_settings({EXT_HUB_KEYS_SETTING: {}})
    assert c.get_extension_hub_key("summarizer")["key"] == "ph_ext_secret"
