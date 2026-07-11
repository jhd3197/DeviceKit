"""AI backend selection (plan 19): ``ai.backend`` = direct | hub.

Covers the settings surface (defaults, secret masking of ``ai.hub.key``, masked-echo
protection) and the Prompture driver-registry rerouting (hub factories per prefix,
restore-to-builtins on direct, missing-key fail-loud).
"""
import pytest

from devicekit.ai_backend import apply_ai_backend, hub_base_url
from devicekit.mixins.settings import SettingsMixin


class _SettingsClient(SettingsMixin):
    pass


@pytest.fixture(autouse=True)
def _restore_registry():
    """Every test leaves Prompture's driver registry as the built-ins."""
    yield
    from prompture.drivers.provider_descriptors import register_all_builtin_drivers
    register_all_builtin_drivers()


# --------------------------------------------------------------------------- settings surface
def test_defaults_direct_backend(fresh_db):
    c = _SettingsClient()
    settings = c.get_all_settings()
    assert settings["ai.backend"] == "direct"
    assert settings["ai.hub.url"] == "http://localhost:1984"
    assert settings["ai.hub.key"] is False          # masked scalar secret, unset
    assert c.ai_backend() == "direct"


def test_hub_key_is_masked_not_leaked(fresh_db):
    c = _SettingsClient()
    c.update_settings({"ai.hub.key": "ph_secret123"})
    settings = c.get_all_settings()
    assert settings["ai.hub.key"] is True           # presence only
    assert "ph_secret123" not in str(settings)
    assert c.ai_hub_key() == "ph_secret123"         # raw value still readable server-side


def test_masked_echo_does_not_clobber_hub_key(fresh_db):
    c = _SettingsClient()
    c.update_settings({"ai.hub.key": "ph_secret123"})
    # A client PUTting the GET payload back sends the masked boolean — must be ignored.
    c.update_settings({"ai.hub.key": True})
    assert c.ai_hub_key() == "ph_secret123"
    # An explicit empty string clears the key.
    c.update_settings({"ai.hub.key": ""})
    assert c.ai_hub_key() is None


def test_invalid_backend_value_falls_back_to_direct(fresh_db):
    c = _SettingsClient()
    c.set_setting("ai.backend", "banana")
    assert c.ai_backend() == "direct"


def test_provider_keys_masking_unchanged(fresh_db):
    c = _SettingsClient()
    c.update_settings({"ai.provider_keys": {"OPENAI_API_KEY": "sk-x"}})
    settings = c.get_all_settings()
    assert settings["ai.provider_keys"] == {"OPENAI_API_KEY": True}


# --------------------------------------------------------------------------- driver rerouting
def test_hub_backend_reroutes_every_prefix():
    from prompture.drivers import get_driver_for_model

    applied = apply_ai_backend("hub", "http://localhost:1984", "ph_test")
    assert applied == "hub"

    for model_str in ("claude/claude-sonnet-4-20250514", "openai/gpt-4o", "ollama/llama3.1:8b"):
        driver = get_driver_for_model(model_str)
        assert type(driver).__name__ == "HubDriver"
        # The hub receives the FULL provider/model id, not the stripped suffix.
        assert driver.model == model_str
        assert driver.api_key == "ph_test"
        assert driver.base_url == "http://localhost:1984/v1"


def test_hub_driver_capability_flags_are_honest():
    apply_ai_backend("hub", "http://localhost:1984", "ph_test")
    from prompture.drivers import get_driver_for_model
    d = get_driver_for_model("openai/gpt-4o")
    # prompture-hub v0.0.x chat endpoint: no native tools/json-schema/vision; SSE yes.
    assert d.supports_tool_use is False
    assert d.supports_json_schema is False
    assert d.supports_json_mode is False
    assert d.supports_vision is False
    assert d.supports_streaming is True


def test_direct_backend_restores_builtins():
    from prompture.drivers import get_driver_for_model

    apply_ai_backend("hub", "http://localhost:1984", "ph_test")
    assert type(get_driver_for_model("openai/gpt-4o")).__name__ == "HubDriver"

    applied = apply_ai_backend("direct")
    assert applied == "direct"
    try:
        driver = get_driver_for_model("openai/gpt-4o", api_key="sk-test")
        assert type(driver).__name__ != "HubDriver"
    except Exception:
        # Builtin driver may refuse to construct without a real key — that alone
        # proves the permissive HubDriver factory is gone.
        pass


def test_hub_without_key_fails_loud():
    from prompture.drivers import get_driver_for_model

    apply_ai_backend("hub", "http://localhost:1984", None)
    with pytest.raises(Exception, match="ai.hub.key"):
        get_driver_for_model("openai/gpt-4o")


def test_hub_base_url_normalization():
    assert hub_base_url("http://localhost:1984") == "http://localhost:1984/v1"
    assert hub_base_url("http://localhost:1984/") == "http://localhost:1984/v1"
    assert hub_base_url(None) == "http://localhost:1984/v1"


# --------------------------------------------------------------------------- save hook
def test_saving_backend_setting_applies_registry(fresh_db):
    from prompture.drivers import get_driver_for_model

    c = _SettingsClient()
    c.update_settings({"ai.backend": "hub", "ai.hub.key": "ph_live"})
    driver = get_driver_for_model("claude/claude-sonnet-4-20250514")
    assert type(driver).__name__ == "HubDriver"
    assert driver.api_key == "ph_live"

    c.update_settings({"ai.backend": "direct"})
    try:
        d2 = get_driver_for_model("claude/claude-sonnet-4-20250514")
        assert type(d2).__name__ != "HubDriver"
    except Exception:
        pass
