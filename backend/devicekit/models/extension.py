"""Installed-extension model (plan 03).

One row per installed extension, keyed by its manifest ``slug``. The full manifest is
stored verbatim (JSON) so the platform can re-derive contribution points, permissions, and
routing after a restart without re-reading the extracted files. ``config`` holds the
user-supplied settings; values whose ``config_schema`` entry is marked ``secret`` are kept
here for the running process but excluded from the serialized ``to_dict`` the API returns.

``sha256`` pins the exact zip bytes that were installed (== the bytes previewed), and
``source_url`` records where they came from so the boot loader can self-heal a missing
extraction by re-downloading.
"""
from sqlalchemy import Column, String, Float, Text, JSON

from devicekit.db import Base


# Lifecycle states. ``active`` routes serve normally; ``disabled`` routes return 503 via the
# status guard without a restart; ``error`` marks an extension that failed to hot-load.
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"


class InstalledExtension(Base):
    __tablename__ = "installed_extensions"

    slug = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    display_name = Column(String, default="")
    category = Column(String, default="utility")
    manifest = Column(JSON, nullable=False)          # full extension.json, verbatim
    config = Column(JSON, default=dict)              # user settings (incl. secrets, in-process)
    permissions = Column(JSON, default=list)         # declared permissions (from manifest)
    url_prefix = Column(String, default="")          # mounted route prefix
    status = Column(String, default=STATUS_ACTIVE)
    source = Column(String, default="")              # 'local' | 'url' | 'upload' | 'builtin' | 'registry'
    source_url = Column(Text, default="")            # re-download origin for self-heal
    sha256 = Column(String, default="")              # pinned zip checksum
    error = Column(Text, default="")                 # last hot-load error, if any
    installed_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    def _secret_keys(self):
        """Config keys the manifest declared ``secret`` — excluded from serialization."""
        schema = (self.manifest or {}).get("config_schema", {}) or {}
        return {k for k, spec in schema.items() if isinstance(spec, dict) and spec.get("secret")}

    def to_dict(self, include_config=True):
        secrets = self._secret_keys()
        cfg = {}
        if include_config:
            for k, v in (self.config or {}).items():
                cfg[k] = "••••••" if k in secrets else v
        return {
            "slug": self.slug,
            "id": self.slug,                          # API addresses extensions by slug
            "version": self.version,
            "display_name": self.display_name or self.slug,
            "category": self.category or "utility",
            "manifest": self.manifest or {},
            "config": cfg,
            "permissions": self.permissions or [],
            "url_prefix": self.url_prefix or "",
            "status": self.status,
            "source": self.source or "",
            "source_url": self.source_url or "",
            "sha256": self.sha256 or "",
            "error": self.error or "",
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
        }
