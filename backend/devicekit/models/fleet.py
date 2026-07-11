"""Fleet domain models: device groups, per-device tags, and saved FQL queries."""
from sqlalchemy import Column, String, Float, Text, JSON

from devicekit.db import Base


class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    color = Column(String, default="#10b981")
    tags = Column(JSON, default=list)
    device_ids = Column(JSON, default=list)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "color": self.color,
            "tags": self.tags or [],
            "device_ids": self.device_ids or [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DeviceTag(Base):
    """One row per device holding its full tag list (mirrors the old
    ``_device_tags`` dict of device_id -> [tag, ...])."""
    __tablename__ = "device_tags"

    device_id = Column(String, primary_key=True)
    tags = Column(JSON, default=list)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    expression = Column(Text, nullable=False)
    description = Column(Text, default="")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "expression": self.expression,
            "description": self.description or "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
