"""FleetPolicy — a persisted ``devicekit.yaml`` desired-state policy (plan 23 part 2).

One row per policy: the raw YAML exactly as the operator wrote it, the normalized spec, a
sha256 hash of the normalized form (the idempotence identity), provenance, and a lifecycle
status. ``applied_hash`` records which spec revision last applied cleanly — the unchanged-hash
short-circuit and the drift check both compare against it.
"""
import time
import uuid

from sqlalchemy import Column, String, Text, Float, Boolean, JSON

from devicekit.db import Base

STATUS_PENDING = "pending"    # never applied, or spec edited since last apply
STATUS_APPLIED = "applied"    # last apply succeeded and no drift observed since
STATUS_DRIFTED = "drifted"    # periodic check found live state diverging from the spec
STATUS_ERROR = "error"        # last apply failed (per-device details in status_detail)
POLICY_STATUSES = (STATUS_PENDING, STATUS_APPLIED, STATUS_DRIFTED, STATUS_ERROR)


class FleetPolicy(Base):
    __tablename__ = "fleet_policies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, default="")
    target_kind = Column(String, nullable=False)    # device | group | fql
    target_value = Column(String, nullable=False)
    raw_yaml = Column(Text, nullable=False)
    normalized = Column(JSON, nullable=False)
    policy_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default=STATUS_PENDING, index=True)
    status_detail = Column(JSON, nullable=True)     # last apply/drift summary or error
    auto_apply = Column(Boolean, nullable=False, default=False)
    source = Column(JSON, nullable=True)            # optional git provenance {repo, ref, commit}
    created_by = Column(String, nullable=True)
    workspace_id = Column(String, nullable=True, index=True)  # NULL = global
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=True)
    applied_at = Column(Float, nullable=True)
    applied_hash = Column(String, nullable=True)
    last_checked_at = Column(Float, nullable=True)  # last drift evaluation

    def to_dict(self, include_spec=False):
        out = {
            "id": self.id,
            "name": self.name or "",
            "target_kind": self.target_kind,
            "target_value": self.target_value,
            "policy_hash": self.policy_hash,
            "status": self.status,
            "status_detail": self.status_detail,
            "auto_apply": bool(self.auto_apply),
            "source": self.source,
            "created_by": self.created_by,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "applied_at": self.applied_at,
            "applied_hash": self.applied_hash,
            "last_checked_at": self.last_checked_at,
        }
        if include_spec:
            out["raw_yaml"] = self.raw_yaml
            out["normalized"] = self.normalized
        return out
