"""A declared agent plugin (plan 25 part 5) — the contract, not a running plugin.

Stores a validated manifest. ``status`` is ``declared`` (the only state that exists yet):
the on-device runtime is deferred, so nothing here ever executes. The row is what an OTA'd
agent or a future sandbox would resolve against.
"""
import time

from sqlalchemy import Column, String, Boolean, Float, JSON

from devicekit.db import Base

STATUS_DECLARED = "declared"


class AgentPlugin(Base):
    __tablename__ = "agent_plugins"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    version = Column(String, nullable=False)
    manifest = Column(JSON, nullable=False)     # normalized manifest
    status = Column(String, nullable=False, default=STATUS_DECLARED)
    enabled = Column(Boolean, default=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)
    workspace_id = Column(String, nullable=True, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "manifest": self.manifest or {},
            "status": self.status,
            "enabled": bool(self.enabled),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace_id": self.workspace_id,
        }
