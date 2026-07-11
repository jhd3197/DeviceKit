"""Channel configuration store (plan 06.2/06.3).

Holds per-channel delivery settings (webhook URL + format, SMTP creds, severity threshold).
Secret keys declared in :data:`CHANNEL_SPECS` are Fernet-encrypted at rest and never returned
by the masked API view. ``get`` returns the decrypted in-process config the consumer needs;
``get_masked`` / ``list_masked`` are what the routes hand back.

Severity gating lives here too: a channel only fires for notifications at or above its
configured ``min_severity`` (info < warning < critical).
"""
import time

from devicekit.db import session_scope
from devicekit.notifications import crypto
from devicekit.models.notification import NotificationChannelConfig

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# Channel metadata: which config keys are secret, and the default config shape.
CHANNEL_SPECS = {
    "webhook": {
        "secret_keys": {"url"},
        "defaults": {"url": "", "format": "slack", "min_severity": "info"},
    },
    "email": {
        "secret_keys": {"smtp_password"},
        "defaults": {
            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": "",
            "from_addr": "", "to_addrs": "", "use_tls": True, "min_severity": "warning",
        },
    },
}

MASK = "••••••"


def _secret_keys(channel):
    return CHANNEL_SPECS.get(channel, {}).get("secret_keys", set())


def _defaults(channel):
    return dict(CHANNEL_SPECS.get(channel, {}).get("defaults", {}))


def severity_ok(min_severity, severity):
    """True if ``severity`` is at or above the channel's ``min_severity``."""
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity or "info", 0)


class NotificationChannelService:

    @classmethod
    def get(cls, channel):
        """Return ``{'channel', 'enabled', 'config'}`` with secrets DECRYPTED (in-process use
        only). Missing rows return spec defaults, disabled."""
        secret_keys = _secret_keys(channel)
        with session_scope() as s:
            row = s.get(NotificationChannelConfig, channel)
            if not row:
                return {"channel": channel, "enabled": False, "config": _defaults(channel)}
            cfg = _defaults(channel)
            cfg.update(row.config or {})
            for k in secret_keys:
                if k in cfg:
                    cfg[k] = crypto.decrypt(cfg[k])
            return {"channel": channel, "enabled": bool(row.enabled), "config": cfg}

    @classmethod
    def get_masked(cls, channel):
        """Same as :meth:`get` but secret values are masked (``••••••`` when set, ``""`` when
        empty) — safe to return over the API."""
        data = cls.get(channel)
        secret_keys = _secret_keys(channel)
        cfg = dict(data["config"])
        for k in secret_keys:
            cfg[k] = MASK if cfg.get(k) else ""
        data["config"] = cfg
        data["secret_keys"] = sorted(secret_keys)
        return data

    @classmethod
    def list_masked(cls):
        return [cls.get_masked(ch) for ch in CHANNEL_SPECS]

    @classmethod
    def set(cls, channel, enabled=None, config=None):
        """Upsert a channel config. Secret keys are encrypted; a secret submitted as the mask
        sentinel (or omitted) keeps the stored value, so the UI can round-trip without leaking
        the secret. Returns the masked view."""
        if channel not in CHANNEL_SPECS:
            raise ValueError(f"Unknown channel: {channel}")
        secret_keys = _secret_keys(channel)
        with session_scope() as s:
            row = s.get(NotificationChannelConfig, channel)
            if not row:
                row = NotificationChannelConfig(channel=channel, config={})
                s.add(row)
            merged = dict(row.config or {})
            if config is not None:
                for k, v in config.items():
                    if k in secret_keys:
                        # Keep existing secret when the client sends the mask or nothing.
                        if v in (None, "", MASK):
                            continue
                        merged[k] = crypto.encrypt(v)
                    else:
                        merged[k] = v
            row.config = merged
            if enabled is not None:
                row.enabled = bool(enabled)
            row.updated_at = time.time()
            s.flush()
        return cls.get_masked(channel)

    @classmethod
    def enabled_channels(cls):
        """List ``{'channel', 'enabled', 'config'}`` (decrypted) for every enabled channel —
        the producer's delivery-planning input."""
        out = []
        for ch in CHANNEL_SPECS:
            data = cls.get(ch)
            if data["enabled"]:
                out.append(data)
        return out
