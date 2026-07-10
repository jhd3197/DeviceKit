"""Plan 08 — metrics history: heartbeat-ingest sampling, tiered period queries, the
raw→hourly→daily rollup, retention prune, threshold alert rules → notification bus, and
derived FQL fields. No daemon threads: rollup/prune/eval are driven synchronously.
"""
import time

import pytest

from devicekit.mixins.metrics_history import (
    MetricsHistoryMixin, parse_period, RAW_RETENTION_S, HOURLY_RETENTION_S,
    DAILY_RETENTION_S, HOUR_S, DAY_S)
from devicekit.mixins.fleet_query import FleetQueryMixin, parse_query, evaluate_ast
from devicekit.models.metrics import DeviceMetricRaw, DeviceMetricHourly, DeviceMetricDaily
from devicekit.db import session_scope


class _Metrics(MetricsHistoryMixin, FleetQueryMixin):
    """Minimal composite: real metrics + FQL, capturing notifications."""

    def __init__(self):
        self.notifications = []
        self.init_metrics()

    def notify_event(self, key, **kwargs):
        self.notifications.append((key, kwargs))
        return {"event_key": key, **kwargs}

    def _agent_device_name(self, device_id):
        return device_id


def _state(battery=None, temp=None, cpu=None, ram_total=None, ram_used=None,
           storage_free=None, network="wifi", screen_on=True):
    metrics = {}
    if battery is not None:
        metrics["battery_level"] = battery
    if temp is not None:
        metrics["battery_temperature"] = temp
    if cpu is not None:
        metrics["cpu_percent"] = cpu
    if ram_total is not None:
        metrics["ram_total_mb"] = ram_total
    if ram_used is not None:
        metrics["ram_used_mb"] = ram_used
    metrics["network"] = {"type": network}
    return {
        "device_id": "dev1",
        "metrics": metrics,
        "storage": {"free": storage_free} if storage_free is not None else {},
        "screen_on": screen_on,
    }


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

def test_parse_period():
    assert parse_period("1h") == 3600
    assert parse_period("24h") == 86400
    assert parse_period("7d") == 604800
    assert parse_period("30d") == 2592000
    assert parse_period("30m") == 1800
    assert parse_period("bogus", default=99) == 99


# ---------------------------------------------------------------------------
# Phase 1 — ingest + period query
# ---------------------------------------------------------------------------

def test_ingest_records_raw_sample(fresh_db):
    c = _Metrics()
    sample = c.record_metrics_sample(
        "dev1", _state(battery=80, temp=30, cpu=12, ram_total=4000, ram_used=1500,
                       storage_free=20000))
    assert sample is not None
    assert sample["battery_pct"] == 80
    assert sample["mem_free"] == 2500  # 4000 - 1500
    assert sample["storage_free"] == 20000
    assert sample["network_type"] == "wifi"

    series = c.get_device_metrics("dev1", metric="battery_pct", period="24h")
    assert series["tier"] == "raw"
    assert len(series["points"]) == 1
    assert series["points"][0]["value"] == 80


def test_ingest_skips_empty_metrics(fresh_db):
    c = _Metrics()
    assert c.record_metrics_sample("dev1", {"device_id": "dev1", "metrics": {}}) is None
    series = c.get_device_metrics("dev1", metric="battery_pct", period="24h")
    assert series["count"] == 0


def test_period_tier_selection(fresh_db):
    c = _Metrics()
    assert c.get_device_metrics("dev1", period="6h")["tier"] == "raw"
    assert c.get_device_metrics("dev1", period="24h")["tier"] == "raw"
    assert c.get_device_metrics("dev1", period="7d")["tier"] == "hourly"
    assert c.get_device_metrics("dev1", period="30d")["tier"] == "daily"


# ---------------------------------------------------------------------------
# Phase 2 — rollup + prune
# ---------------------------------------------------------------------------

def test_rollup_raw_to_hourly_to_daily(fresh_db):
    c = _Metrics()
    now = time.time()
    # Two raw samples in the same hour bucket, averaged: (40 + 60) / 2 = 50.
    bucket = int(now // HOUR_S) * HOUR_S
    with session_scope() as s:
        s.add(DeviceMetricRaw(device_id="dev1", ts=bucket + 10, battery_pct=40, cpu_load=10))
        s.add(DeviceMetricRaw(device_id="dev1", ts=bucket + 20, battery_pct=60, cpu_load=30))

    result = c.rollup_metrics()
    assert result["hourly_buckets"] == 1
    assert result["daily_buckets"] == 1

    with session_scope() as s:
        h = s.query(DeviceMetricHourly).one()
        assert h.battery_pct == 50
        assert h.cpu_load == 20
        assert h.samples == 2
        assert h.ts == bucket
        d = s.query(DeviceMetricDaily).one()
        assert d.battery_pct == 50

    # Idempotent: a second rollup must not duplicate buckets.
    c.rollup_metrics()
    with session_scope() as s:
        assert s.query(DeviceMetricHourly).count() == 1
        assert s.query(DeviceMetricDaily).count() == 1


def test_prune_retention(fresh_db):
    c = _Metrics()
    now = time.time()
    with session_scope() as s:
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - RAW_RETENTION_S - 100, battery_pct=1))
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - 100, battery_pct=2))  # fresh
        s.add(DeviceMetricHourly(device_id="dev1", ts=now - HOURLY_RETENTION_S - 100,
                                 battery_pct=1, samples=1))
        s.add(DeviceMetricDaily(device_id="dev1", ts=now - DAILY_RETENTION_S - 100,
                                battery_pct=1, samples=1))

    removed = c.prune_metrics()
    assert removed["raw"] == 1
    assert removed["hourly"] == 1
    assert removed["daily"] == 1
    with session_scope() as s:
        assert s.query(DeviceMetricRaw).count() == 1  # the fresh one survives


def test_fleet_metrics_and_sparklines(fresh_db):
    c = _Metrics()
    c.record_metrics_sample("dev1", _state(battery=90))
    c.record_metrics_sample("dev2", _state(battery=50))
    fleet = c.get_fleet_metrics(metric="battery_pct", device_ids=["dev1", "dev2"], period="24h")
    assert fleet["count"] == 2
    spark = c.get_fleet_sparklines(metric="battery_pct", device_ids=["dev1", "dev2"])
    assert spark["sparklines"]["dev1"] == [90]
    assert spark["sparklines"]["dev2"] == [50]


# ---------------------------------------------------------------------------
# Phase 4 — threshold alert rules
# ---------------------------------------------------------------------------

def test_default_rule_seeded(fresh_db):
    c = _Metrics()
    rules = c.list_metric_alert_rules()
    assert any(r["metric"] == "battery_pct" and r["op"] == "<" for r in rules)


def test_alert_rule_fires_notification(fresh_db):
    c = _Metrics()
    # The seeded battery_pct < 20 rule should fire on a 10% sample.
    c.record_metrics_sample("dev1", _state(battery=10, cpu=5))
    keys = [k for k, _ in c.notifications]
    assert "device.battery.low" in keys


def test_alert_rule_cooldown(fresh_db):
    c = _Metrics()
    c.record_metrics_sample("dev1", _state(battery=10))
    c.record_metrics_sample("dev1", _state(battery=9))  # within cooldown → no second notify
    assert len([k for k, _ in c.notifications if k == "device.battery.low"]) == 1


def test_custom_rule_crud_and_eval(fresh_db):
    c = _Metrics()
    rule = c.create_metric_alert_rule(
        metric="battery_temp", op=">", value=45, event_key="device.metric.threshold",
        cooldown_seconds=0)
    assert rule["id"]
    c.record_metrics_sample("dev1", _state(battery=80, temp=50))
    assert any(k == "device.metric.threshold" for k, _ in c.notifications)

    assert c.delete_metric_alert_rule(rule["id"]) is True
    assert c.get_metric_alert_rule(rule["id"]) is None

    with pytest.raises(ValueError):
        c.create_metric_alert_rule("battery_pct", "??", 1, "e")


# ---------------------------------------------------------------------------
# Phase 4 — FQL derived fields
# ---------------------------------------------------------------------------

def test_fql_storage_free_gb(fresh_db):
    c = _Metrics()
    c.record_metrics_sample("dev1", _state(battery=80, storage_free=10240))  # 10 GB
    device = {"device_id": "dev1"}
    ast = parse_query("storage.free_gb > 5")
    assert evaluate_ast(ast, device, fleet_mixin=c) is True
    ast2 = parse_query("storage.free_gb > 50")
    assert evaluate_ast(ast2, device, fleet_mixin=c) is False


def test_fql_battery_trend_24h(fresh_db):
    c = _Metrics()
    now = time.time()
    with session_scope() as s:
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - 1000, battery_pct=80))
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - 10, battery_pct=60))
    device = {"device_id": "dev1"}
    ast = parse_query("battery.trend_24h < 0")  # draining
    assert evaluate_ast(ast, device, fleet_mixin=c) is True


def test_fql_cpu_load_1h_avg(fresh_db):
    c = _Metrics()
    now = time.time()
    with session_scope() as s:
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - 60, cpu_load=2.0))
        s.add(DeviceMetricRaw(device_id="dev1", ts=now - 30, cpu_load=4.0))
    device = {"device_id": "dev1"}
    ast = parse_query("metrics.cpu_load_1h_avg > 2.0")
    assert evaluate_ast(ast, device, fleet_mixin=c) is True
