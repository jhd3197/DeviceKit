"""Per-extension LLM access — the plan-19 security payoff.

Extensions that declare the ``llm`` permission call the model through
``sdk.ai(slug).ask(...)`` / ``.conversation(...)``, which lands here. What credentials
serve the call depends on ``ai.backend``:

- ``hub``: each extension gets its **own** hub key, created through the hub's admin API
  (gated by ``HUB_ADMIN_TOKEN``, env-only) and scoped by an allowed-model whitelist +
  daily spend cap from the extension's manifest (``llm_allowed_models`` /
  ``llm_daily_cap_usd``, consented at install like every other manifest claim). The
  extension can't see host provider secrets, can't exceed its cap, and uninstall revokes
  the key — instant lockout, no provider-key rotation.
- ``direct``: there is nothing to scope with, so the call runs on the host's Prompture
  config (provider keys in env) with a warning logged. Decision per plan 19: host-key-
  with-warning for continuity; per-extension isolation requires the hub.

Key material lives in the ``ai.hub.extension_keys`` setting — server-managed (the
settings API refuses client writes to it), masked on read like every other secret.
"""
import logging
import time

logger = logging.getLogger(__name__)

EXT_HUB_KEYS_SETTING = "ai.hub.extension_keys"

# Conservative default when a manifest declares ``llm`` but no cap — matches the hub's
# own default.
DEFAULT_EXT_DAILY_CAP_USD = 1.0


class ExtensionAiMixin:
    """Per-extension hub keys + the LLM call surface behind ``sdk.ai(slug)``."""

    # ------------------------------------------------------------------
    # Key lifecycle
    # ------------------------------------------------------------------
    def get_extension_hub_key(self, slug):
        """The stored hub-key record for ``slug`` (``{id, key, allowed_models,
        daily_spend_cap_usd, created_at}``), or None."""
        keys = self.get_setting(EXT_HUB_KEYS_SETTING) or {}
        return keys.get(slug)

    def ensure_extension_hub_key(self, slug):
        """Create (or return the existing) scoped hub key for an ``llm`` extension.
        No-op returning None unless the hub backend is active and ``HUB_ADMIN_TOKEN``
        is set. Never raises — install and first-use paths call this best-effort."""
        from devicekit.ai_backend import create_hub_key, hub_admin_token

        if self.ai_backend() != "hub":
            return None
        existing = self.get_extension_hub_key(slug)
        if existing:
            return existing

        admin_token = hub_admin_token()
        if not admin_token:
            logger.warning(
                f"Extension '{slug}' declares llm and the hub backend is active, but "
                f"HUB_ADMIN_TOKEN is not set — cannot issue a scoped key; calls will "
                f"fall back to the host hub key.")
            return None

        row = self.get_extension(slug) if hasattr(self, "get_extension") else None
        manifest = (row or {}).get("manifest") or {}
        allowed_models = manifest.get("llm_allowed_models") or []
        try:
            cap = float(manifest.get("llm_daily_cap_usd") or DEFAULT_EXT_DAILY_CAP_USD)
        except (TypeError, ValueError):
            cap = DEFAULT_EXT_DAILY_CAP_USD

        try:
            created = create_hub_key(
                self.ai_hub_url(), admin_token, name=f"devicekit-ext:{slug}",
                allowed_models=allowed_models, daily_spend_cap_usd=cap)
        except Exception as e:
            logger.warning(f"Creating hub key for extension '{slug}' failed: {e}")
            return None

        record = {
            "id": created.get("id"),
            "key": created.get("key"),
            "allowed_models": allowed_models,
            "daily_spend_cap_usd": cap,
            "created_at": time.time(),
        }
        keys = dict(self.get_setting(EXT_HUB_KEYS_SETTING) or {})
        keys[slug] = record
        self.set_setting(EXT_HUB_KEYS_SETTING, keys)
        logger.info(
            f"Issued scoped hub key for extension '{slug}' "
            f"(models: {allowed_models or 'all'}, cap ${cap}/day)")
        return record

    def revoke_extension_hub_key(self, slug):
        """Revoke ``slug``'s hub key (uninstall path). Best-effort on the hub side; the
        stored record is removed either way so a reinstall issues a fresh key."""
        from devicekit.ai_backend import hub_admin_token, revoke_hub_key

        keys = dict(self.get_setting(EXT_HUB_KEYS_SETTING) or {})
        record = keys.pop(slug, None)
        if record is None:
            return False
        self.set_setting(EXT_HUB_KEYS_SETTING, keys)

        admin_token = hub_admin_token()
        if admin_token and record.get("id") is not None:
            try:
                revoke_hub_key(self.ai_hub_url(), admin_token, record["id"])
                logger.info(f"Revoked hub key for extension '{slug}'")
            except Exception as e:
                logger.warning(f"Revoking hub key for '{slug}' on the hub failed: {e}")
        return True

    # ------------------------------------------------------------------
    # LLM call surface (behind sdk.ai(slug))
    # ------------------------------------------------------------------
    def extension_ai_conversation(self, slug, model=None, system_prompt=None):
        """A Prompture Conversation for an extension, on that extension's credentials
        where possible. The SDK enforces the ``llm`` permission before calling in; this
        re-checks so no host path can bypass it."""
        from devicekit_sdk.permissions import require
        require(slug, "llm")

        from prompture import Conversation
        model = model or self.ai_default_model()

        if self.ai_backend() == "hub":
            record = self.get_extension_hub_key(slug) or self.ensure_extension_hub_key(slug)
            if record and record.get("key"):
                from devicekit.ai_backend import make_extension_driver
                driver = make_extension_driver(self.ai_hub_url(), record["key"], model)
                return Conversation(driver=driver, system_prompt=system_prompt)
            logger.warning(
                f"Extension '{slug}' LLM call using the HOST hub key (no scoped key "
                f"available — set HUB_ADMIN_TOKEN to isolate extensions).")
            # Registry is already hub-routed, so plain model resolution hits the hub.
            return Conversation(model_name=model, system_prompt=system_prompt)

        logger.warning(
            f"Extension '{slug}' LLM call using host provider credentials — no cap or "
            f"isolation on the direct backend; switch ai.backend to 'hub' for "
            f"per-extension keys.")
        return Conversation(model_name=model, system_prompt=system_prompt)

    def extension_ai_ask(self, slug, prompt, model=None, system_prompt=None):
        """One-shot ask on a fresh conversation — the common extension case."""
        return self.extension_ai_conversation(
            slug, model=model, system_prompt=system_prompt).ask(prompt)
