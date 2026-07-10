"""Visual-regression baseline model.

The baseline screenshot bytes live in a BLOB column (baselines are single screenshots,
comfortably small for SQLite). ``to_dict()`` defaults to the metadata-only shape the API
returns; internal callers that need the pixels pass ``include_image=True`` to get the
``image_b64`` field the comparison code expects.
"""
import base64

from sqlalchemy import Column, String, Float, Integer, LargeBinary, JSON

from devicekit.db import Base


class VisualBaseline(Base):
    __tablename__ = "visual_baselines"

    id = Column(String, primary_key=True)
    automation_id = Column(String, index=True)
    step_index = Column(Integer, default=0)
    device_model = Column(String, default="default")
    resolution = Column(String, default="default")
    label = Column(String, default="")
    image_data = Column(LargeBinary, nullable=True)
    image_size = Column(Integer, default=0)
    mask_regions = Column(JSON, default=list)
    version = Column(Integer, default=1)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)

    def to_dict(self, include_image=False):
        data = {
            "id": self.id,
            "automation_id": self.automation_id,
            "step_index": self.step_index,
            "device_model": self.device_model,
            "resolution": self.resolution,
            "label": self.label,
            "image_size": self.image_size or 0,
            "mask_regions": self.mask_regions or [],
            "version": self.version or 1,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_image:
            data["image_b64"] = (
                base64.b64encode(self.image_data).decode("ascii") if self.image_data else ""
            )
        return data
