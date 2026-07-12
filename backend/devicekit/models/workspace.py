"""Workspaces, membership & resource grants (plan 20, part 4).

The multi-user payoff, ported from ServerKit's tenancy model. A ``Workspace`` scopes *devices +
automations*; ``WorkspaceMember`` is the per-user membership (one row per pair) whose role folds
into a **highest-wins** tier (viewer < member < admin < owner). ``ResourceGrant`` is the escape
hatch — share a *single* device or automation with a teammate (widens visibility only) without
whole-fleet membership.

Devices are enrolled agents, not user-owned, so ``AgentDevice`` carries ``workspace_id`` directly
("born-in-workspace"); ``Automation``/``SavedQuery`` do too. Their children derive scope through
``device_id`` and are never assigned a workspace of their own.
"""
import time
import uuid

from sqlalchemy import Column, String, Float, Integer, UniqueConstraint

from devicekit.db import Base

WORKSPACE_STATUSES = ("active", "archived")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="active")
    # Quota fields exist (schema-compatible with ServerKit) but are NOT enforced in this plan.
    max_devices = Column(Integer, nullable=True)
    max_members = Column(Integer, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "max_devices": self.max_devices,
            "max_members": self.max_members,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")  # owner | admin | member | viewer
    created_at = Column(Float, nullable=False, default=time.time)

    def to_dict(self):
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "role": self.role,
            "created_at": self.created_at,
        }


class ResourceGrant(Base):
    """Share a single device/automation with a user; widens *visibility* only, never permission."""

    __tablename__ = "resource_grants"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "user_id", name="uq_resource_grant"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    resource_type = Column(String, nullable=False, index=True)   # device | automation
    resource_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    level = Column(String, nullable=False, default="viewer")     # viewer | editor
    granted_by = Column(String, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)

    def to_dict(self):
        return {
            "id": self.id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "level": self.level,
            "granted_by": self.granted_by,
            "created_at": self.created_at,
        }
