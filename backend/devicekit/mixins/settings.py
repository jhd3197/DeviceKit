"""Durable app settings — the service layer behind ``GET/PUT /settings`` (plan 12).

A tiny namespaced key/value store (``Setting`` rows) that lets the Settings UI edit values
that used to require a ``.env`` edit or lived only in the in-memory ``_config`` dict. Every
key has a declared default in ``SETTINGS_DEFAULTS`` so a fresh DB returns a fully-populated
settings object and callers never special-case ``None``.

Other mixins read effective values through the small helpers here (``ai_default_model``,
``streaming_defaults``, ``bundle_retention_days``, ``share_token_lifetime_minutes``) so a
saved setting overrides the ``config.py`` / hard-coded fallback without them each learning
the settings schema. Provider API keys are pushed into ``os.environ`` on boot and on save
so Prompture (which reads keys from the environment) picks them up with no restart.
"""
import os
import time
import logging

from devicekit.db import session_scope
from devicekit.models import Setting

logger = logging.getLogger(__name__)

# Declared settings surface: dotted key -> default value. GET /settings always returns
# every key (persisted value or this default); PUT /settings only accepts keys listed here
# so the store can't be scribbled full of arbitrary junk from the client.
SETTINGS_DEFAULTS = {
    # General
    "general.instance_name": "DeviceKit",
    "general.default_device_timeout": 30,      # seconds, per-command dispatch
    # AI (Prompture)
    "ai.default_model": None,                  # None => fall back to PROMPTURE_DEFAULT_MODEL
    "ai.model_overrides": {},                  # {generation, self_heal, analysis} -> model id
    "ai.provider_keys": {},                    # {ENV_VAR: value} pushed into os.environ
    "ai.default_agent_mode": "supervised",     # observe | supervised | autonomous (per-device default)
    "ai.gate_timeout_seconds": 120,            # confirmation gate deadline; default-deny on expiry
    # Streaming
    "streaming.default_fps": 10,
    "streaming.default_quality": 50,
    "streaming.recording_retention_days": 14,
    # Debug bundles
    "bundles.retention_days": 30,
    "bundles.share_token_lifetime_minutes": 1440,   # 24h
    # Appearance
    "appearance.theme": "dark",
    "appearance.accent": "#10b981",            # emerald — DeviceKit's historical accent
}

# Keys whose values are secret-ish (never echo the raw value back to the client). Their
# presence is reported as a boolean per env var instead.
_SECRET_KEYS = {"ai.provider_keys"}


class SettingsMixin:
    """CRUD + typed accessors for durable app settings."""

    def init_settings(self):
        """Apply any persisted provider keys to the environment at boot. Idempotent."""
        try:
            self._apply_provider_keys(self.get_setting("ai.provider_keys") or {})
        except Exception as e:  # a broken settings row must never block boot
            logger.warning(f"Settings init skipped: {e}")

    # -----------------------------------------------------------
    # Core store
    # -----------------------------------------------------------

    def get_setting(self, key, default=None):
        """Return one setting's effective value: persisted, else declared default, else
        the passed ``default``."""
        with session_scope() as s:
            row = s.get(Setting, key)
            if row is not None:
                return row.value
        if key in SETTINGS_DEFAULTS:
            return SETTINGS_DEFAULTS[key]
        return default

    def get_all_settings(self, redact=True):
        """Return the full settings object: every declared key merged with persisted
        overrides. Secret values are redacted to booleans when ``redact`` is set."""
        values = dict(SETTINGS_DEFAULTS)
        with session_scope() as s:
            for row in s.query(Setting).all():
                if row.key in SETTINGS_DEFAULTS:
                    values[row.key] = row.value
        if redact:
            for key in _SECRET_KEYS:
                raw = values.get(key) or {}
                # Report which provider keys are set without leaking the secret.
                values[key] = {name: bool(v) for name, v in raw.items()}
        return values

    def set_setting(self, key, value):
        """Upsert a single setting. Rejects keys outside the declared surface."""
        if key not in SETTINGS_DEFAULTS:
            raise ValueError(f"Unknown setting key: {key}")
        with session_scope() as s:
            row = s.get(Setting, key)
            if row is None:
                row = Setting(key=key)
                s.add(row)
            row.value = value
            row.updated_at = time.time()
        if key == "ai.provider_keys":
            self._apply_provider_keys(value or {})
        return value

    def update_settings(self, data):
        """Merge a flat ``{key: value}`` map, ignoring unknown keys. Provider keys are
        merged (blank value clears a key) rather than replaced wholesale so the UI can send
        only the fields it changed. Returns the fresh redacted settings object."""
        if not isinstance(data, dict):
            raise ValueError("settings payload must be an object")
        for key, value in data.items():
            if key not in SETTINGS_DEFAULTS:
                continue
            if key == "ai.provider_keys" and isinstance(value, dict):
                value = self._merge_provider_keys(value)
            self.set_setting(key, value)
        return self.get_all_settings()

    # -----------------------------------------------------------
    # Provider-key handling
    # -----------------------------------------------------------

    def _merge_provider_keys(self, incoming):
        """Merge incoming ``{ENV_VAR: value}`` onto the stored map. An empty/blank value
        removes that env var so the UI can clear a key."""
        current = dict(self.get_setting("ai.provider_keys") or {})
        for name, value in incoming.items():
            if value:
                current[name] = value
            else:
                current.pop(name, None)
        return current

    def _apply_provider_keys(self, keys):
        """Push provider keys into ``os.environ`` so Prompture picks them up live."""
        for name, value in (keys or {}).items():
            if value:
                os.environ[name] = value

    # -----------------------------------------------------------
    # Typed accessors used by other mixins
    # -----------------------------------------------------------

    def ai_default_model(self):
        """Effective default model: saved setting, else ``PROMPTURE_DEFAULT_MODEL``."""
        model = self.get_setting("ai.default_model")
        if model:
            return model
        from config import PROMPTURE_DEFAULT_MODEL
        return PROMPTURE_DEFAULT_MODEL

    def ai_model_for(self, feature):
        """Per-feature model override (generation | self_heal | analysis), else default."""
        overrides = self.get_setting("ai.model_overrides") or {}
        return overrides.get(feature) or self.ai_default_model()

    def ai_default_agent_mode(self):
        """Fallback session mode when a device has no per-profile agent_mode."""
        mode = self.get_setting("ai.default_agent_mode") or "supervised"
        return mode if mode in ("observe", "supervised", "autonomous") else "supervised"

    def ai_gate_timeout_seconds(self):
        """Seconds the confirmation gate waits for a human before default-denying."""
        try:
            return max(1, int(self.get_setting("ai.gate_timeout_seconds") or 120))
        except (TypeError, ValueError):
            return 120

    def streaming_defaults(self):
        """Return ``(fps, quality)`` defaults for new stream/recording sessions."""
        return (
            int(self.get_setting("streaming.default_fps") or 10),
            int(self.get_setting("streaming.default_quality") or 50),
        )

    def bundle_retention_days(self):
        return int(self.get_setting("bundles.retention_days") or 30)

    def share_token_lifetime_minutes(self):
        return int(self.get_setting("bundles.share_token_lifetime_minutes") or 1440)
