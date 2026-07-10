"""Durable app-settings model — a tiny namespaced key/value store (plan 12).

Settings that used to live only in ``.env`` (AI provider/model) or in the in-memory
``_config`` dict now persist here so the Settings UI can edit them without a redeploy.
Keys are dotted namespaces (``ai.default_model``, ``streaming.default_fps``,
``appearance.accent``); values are JSON so a key can hold a scalar or a nested object
(per-feature model overrides, provider-key maps).
"""
import time

from sqlalchemy import Column, String, Float, JSON

from devicekit.db import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(120), primary_key=True)
    value = Column(JSON, nullable=True)
    updated_at = Column(Float, default=time.time)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at,
        }
