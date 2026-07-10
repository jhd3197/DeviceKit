"""Failure debug-bundle metadata model.

The ZIP payload belongs in object storage, so it is written to disk under
``output/debug_bundles/<id>.zip`` and this row keeps only metadata (plus a pointer). That
keeps the DB small and matches the plan's "ZIP bytes -> disk or S3" guidance.
"""
from sqlalchemy import Column, String, Float, Integer, Text, JSON

from devicekit.db import Base


class DebugBundle(Base):
    __tablename__ = "debug_bundles"

    id = Column(String, primary_key=True)
    device_id = Column(String, index=True)
    trigger = Column(String, default="manual", index=True)
    context = Column(JSON, default=dict)
    files = Column(JSON, default=list)
    size_bytes = Column(Integer, default=0)
    created_at = Column(Float, nullable=False, index=True)
    generation_ms = Column(Integer, default=0)
    ai_analysis = Column(JSON, nullable=True)
    zip_path = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "trigger": self.trigger,
            "context": self.context or {},
            "files": self.files or [],
            "size_bytes": self.size_bytes or 0,
            "created_at": self.created_at,
            "generation_ms": self.generation_ms or 0,
            "ai_analysis": self.ai_analysis,
        }
