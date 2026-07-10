"""Threshold alert rules on device metrics (plan 08 phase 4).

A rule is a simple ``metric op value → event_key`` row (ServerKit's ``metric_alert.py``
ported): evaluated against every metrics sample at heartbeat-ingest, a match emits through
the plan 06 notification bus (``device.battery.critical``, ``device.storage.low``, or any
custom event key). ``device_id`` scopes a rule to one device; ``NULL`` applies it fleet-wide.
``cooldown_seconds`` (enforced in-memory by the mixin) debounces so a metric hovering at a
threshold notifies once, not every heartbeat.
"""
import uuid

from sqlalchemy import Column, String, Float, Boolean, Integer

from devicekit.db import Base


class MetricAlertRule(Base):
    __tablename__ = "metric_alert_rules"

    OPS = ("<", "<=", ">", ">=", "=", "!=")

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    metric = Column(String, nullable=False)             # e.g. battery_pct, storage_free
    op = Column(String, nullable=False)                 # one of OPS
    value = Column(Float, nullable=False)
    event_key = Column(String, nullable=False)          # catalog event to emit on match
    severity = Column(String, nullable=True)            # override catalog severity
    device_id = Column(String, nullable=True, index=True)  # None = fleet-wide
    enabled = Column(Boolean, default=True, nullable=False)
    cooldown_seconds = Column(Integer, default=300, nullable=False)
    created_at = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "metric": self.metric,
            "op": self.op,
            "value": self.value,
            "event_key": self.event_key,
            "severity": self.severity,
            "device_id": self.device_id,
            "enabled": bool(self.enabled),
            "cooldown_seconds": self.cooldown_seconds,
            "created_at": self.created_at,
        }
