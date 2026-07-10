"""Device metrics history — tiered time-series tables (plan 08).

Agent heartbeats already carry rich device state (battery, thermals, CPU, memory,
storage, network); plan 08 persists a **sample** on each heartbeat instead of keeping only
the latest snapshot in memory. Three tiers keep storage bounded regardless of fleet size ×
uptime (the ServerKit ``metrics_history_service`` pattern):

* ``device_metrics_raw`` — one row per heartbeat, retained ~24h.
* ``device_metrics_hourly`` — raw rows averaged into hour buckets, retained ~7d.
* ``device_metrics_daily`` — hourly rows averaged into day buckets, retained ~30d.

The rollup/prune scheduled jobs (plan 05) aggregate raw→hourly→daily and trim each tier.
A period query (``?period=1h|24h|7d|30d``) transparently picks the right tier. The numeric
columns are the fields Phase 22's predictive layer (battery degradation, storage fill-rate,
thermal throttling) needs; ``extra`` (JSON) lets plan 03 extensions contribute samples
without a schema change. ``samples`` on the rollup tiers records how many raw rows an
average covers (weighting for a future weighted re-roll / confidence).

Timestamps are epoch seconds (``time.time()``), matching the rest of the API. The rollup
tiers store the **bucket start** as ``ts`` so a bucket upserts idempotently.
"""
from sqlalchemy import Column, String, Float, Boolean, Integer, JSON, Index

from devicekit.db import Base


# The numeric metric columns shared by all three tiers (rollups store averages of these).
METRIC_NUMERIC_COLUMNS = (
    "battery_pct", "battery_temp", "cpu_load", "mem_free", "storage_free",
)


class _MetricSampleMixin:
    """Shared columns for the raw + rollup metric tables."""

    device_id = Column(String, nullable=False, index=True)
    ts = Column(Float, nullable=False, index=True)  # epoch seconds (raw) / bucket start (rollup)

    battery_pct = Column(Float, nullable=True)      # 0-100
    battery_temp = Column(Float, nullable=True)     # Celsius
    cpu_load = Column(Float, nullable=True)         # percent 0-100
    mem_free = Column(Float, nullable=True)         # MB free
    storage_free = Column(Float, nullable=True)     # MB free
    network_type = Column(String, nullable=True)    # wifi / cellular / ...
    screen_on = Column(Boolean, nullable=True)

    # Extension-reported metrics (plan 03) — arbitrary numeric samples keyed by name.
    extra = Column(JSON, nullable=True)

    def _base_dict(self):
        return {
            "device_id": self.device_id,
            "ts": self.ts,
            "battery_pct": self.battery_pct,
            "battery_temp": self.battery_temp,
            "cpu_load": self.cpu_load,
            "mem_free": self.mem_free,
            "storage_free": self.storage_free,
            "network_type": self.network_type,
            "screen_on": self.screen_on,
            "extra": self.extra or {},
        }


class DeviceMetricRaw(_MetricSampleMixin, Base):
    __tablename__ = "device_metrics_raw"

    id = Column(Integer, primary_key=True, autoincrement=True)

    __table_args__ = (
        Index("ix_device_metrics_raw_device_ts", "device_id", "ts"),
    )

    def to_dict(self):
        d = self._base_dict()
        d["id"] = self.id
        return d


class DeviceMetricHourly(_MetricSampleMixin, Base):
    __tablename__ = "device_metrics_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    samples = Column(Integer, default=0)  # raw rows averaged into this bucket

    __table_args__ = (
        Index("ix_device_metrics_hourly_device_ts", "device_id", "ts", unique=True),
    )

    def to_dict(self):
        d = self._base_dict()
        d["id"] = self.id
        d["samples"] = self.samples
        return d


class DeviceMetricDaily(_MetricSampleMixin, Base):
    __tablename__ = "device_metrics_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    samples = Column(Integer, default=0)  # hourly rows averaged into this bucket

    __table_args__ = (
        Index("ix_device_metrics_daily_device_ts", "device_id", "ts", unique=True),
    )

    def to_dict(self):
        d = self._base_dict()
        d["id"] = self.id
        d["samples"] = self.samples
        return d
