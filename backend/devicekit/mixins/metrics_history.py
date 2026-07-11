"""MetricsHistoryMixin — device metrics history, rollups, and threshold alerts (plan 08).

DeviceKit agents already report rich state on every heartbeat; this mixin turns that stream
into bounded time-series history (the ServerKit ``metrics_history_service`` pattern):

* **Ingest** — ``record_metrics_sample`` persists one ``DeviceMetricRaw`` row per heartbeat
  (no new polling) and evaluates threshold alert rules. Called from the ``/agent-device/state``
  route. Never raises: a metrics problem must not sink a heartbeat.
* **Rollup / prune** — ``rollup_metrics`` averages raw→hourly→daily; ``prune_metrics`` trims
  each tier to its retention window (raw 24h, hourly 7d, daily 30d). Both run as ``metrics.*``
  scheduled jobs (plan 05) registered in ``init_metrics``. Storage stays bounded regardless
  of fleet size × uptime.
* **Query** — ``get_device_metrics`` / ``get_fleet_metrics`` pick the right tier for a
  ``period`` transparently; ``get_fleet_sparklines`` feeds the inline dashboard sparklines.
* **Threshold alerts** — a ``metric op value → event_key`` rules table (plan 06 bus),
  cooldown-debounced in memory.
* **FQL** — derived history fields (``battery.trend_24h``, ``storage.free_gb``,
  ``metrics.cpu_load_1h_avg``) registered onto the fleet-query registry so history is
  queryable.

Composed in ``client.py`` before ``ApiAppMixin``; ``init_metrics`` runs after ``init_jobs``
(so the rollup/prune job kinds and schedules can register onto the live job system) and after
``init_persistence``.
"""
import time
import logging
import threading

from sqlalchemy import delete

from devicekit.db import session_scope
from devicekit.models.metrics import (
    DeviceMetricRaw, DeviceMetricHourly, DeviceMetricDaily, METRIC_NUMERIC_COLUMNS)
from devicekit.models.metric_alert import MetricAlertRule

logger = logging.getLogger(__name__)

# Retention windows per tier (seconds). Raw keeps 24h of minute-resolution samples so the
# Phase 22 predictive layer has enough resolution; hourly/daily bound long-range history.
RAW_RETENTION_S = 24 * 3600
HOURLY_RETENTION_S = 7 * 24 * 3600
DAILY_RETENTION_S = 30 * 24 * 3600

HOUR_S = 3600
DAY_S = 86400

# Metrics exposed to queries: the numeric sample columns.
QUERYABLE_METRICS = set(METRIC_NUMERIC_COLUMNS)

_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_period(period, default=86400):
    """Parse a period string (``30m``/``6h``/``7d``/``4w``) into seconds. Falls back to
    ``default`` on anything unrecognized."""
    if not period:
        return default
    period = str(period).strip().lower()
    try:
        if period[-1] in _UNIT_SECONDS:
            return max(1, int(float(period[:-1]) * _UNIT_SECONDS[period[-1]]))
        return max(1, int(float(period)))  # bare number = seconds
    except (ValueError, IndexError):
        return default


class MetricsHistoryMixin:
    _metrics_ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_metrics(self):
        """Register the rollup/prune job kinds + schedules, seed default alert rules, and
        register the derived FQL fields. Idempotent; starts no threads."""
        if self._metrics_ready:
            return
        self._metric_alert_last_fired = {}  # (rule_id, device_id) -> epoch
        self._metric_alert_lock = threading.Lock()
        try:
            if hasattr(self, "register_job_kind"):
                self.register_job_kind("metrics.rollup", self._job_rollup_metrics)
                self.register_job_kind("metrics.prune", self._job_prune_metrics)
            if hasattr(self, "ensure_scheduled_job"):
                # Rollup every 5 min; prune hourly (retention is coarse, no need to run often).
                self.ensure_scheduled_job(
                    "metrics.rollup", "metrics.rollup",
                    interval_seconds=300, startup_delay_seconds=120,
                    owner_type="system", owner_id="core")
                self.ensure_scheduled_job(
                    "metrics.prune", "metrics.prune",
                    interval_seconds=3600, startup_delay_seconds=1800,
                    owner_type="system", owner_id="core")
        except Exception as e:
            logger.warning("Metrics housekeeping not scheduled: %s", e)

        try:
            self.seed_default_metric_alert_rules()
        except Exception as e:
            logger.warning("Default metric alert rules not seeded: %s", e)

        try:
            self._register_metric_fql_fields()
        except Exception as e:
            logger.warning("Metric FQL fields not registered: %s", e)

        self._metrics_ready = True
        logger.info("Metrics history initialized (queryable: %s)",
                    ", ".join(sorted(QUERYABLE_METRICS)))

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_sample(state):
        """Map an agent state dict (as posted to /agent-device/state) to sample columns.

        Tolerant of the two shapes the agent uses: metrics under ``state['metrics']`` and
        storage either under ``state['storage']`` or ``state['metrics']['storage']``.
        """
        state = state or {}
        metrics = state.get("metrics") or {}
        network = metrics.get("network") or {}
        storage = state.get("storage") or metrics.get("storage") or {}

        ram_total = metrics.get("ram_total_mb")
        ram_used = metrics.get("ram_used_mb")
        mem_free = None
        if ram_total is not None and ram_used is not None:
            mem_free = max(0.0, float(ram_total) - float(ram_used))
        elif metrics.get("ram_free_mb") is not None:
            mem_free = float(metrics.get("ram_free_mb"))

        storage_free = storage.get("free")
        if storage_free is None:
            storage_free = metrics.get("storage_free_mb")

        screen_on = state.get("screen_on")
        if screen_on is None:
            screen_on = metrics.get("screen_on")

        def _num(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        return {
            "battery_pct": _num(metrics.get("battery_level")),
            "battery_temp": _num(metrics.get("battery_temperature")),
            "cpu_load": _num(metrics.get("cpu_percent")),
            "mem_free": _num(mem_free),
            "storage_free": _num(storage_free),
            "network_type": network.get("type") if isinstance(network, dict) else None,
            "screen_on": bool(screen_on) if screen_on is not None else None,
            "extra": metrics.get("extra") or state.get("extension_metrics") or {},
        }

    def record_metrics_sample(self, device_id, state, ts=None):
        """Persist one raw metrics sample from an agent heartbeat and evaluate alert rules.

        Cheap (a single insert) and defensive — any failure is logged, never raised, so the
        heartbeat path is unaffected. Returns the persisted sample dict, or ``None`` if there
        was nothing numeric to record.
        """
        if not device_id:
            return None
        try:
            cols = self._extract_sample(state)
            # Skip a heartbeat that carried no metrics at all (avoids empty rows).
            if all(cols.get(c) is None for c in METRIC_NUMERIC_COLUMNS):
                return None
            now = ts if ts is not None else time.time()
            with session_scope() as s:
                row = DeviceMetricRaw(device_id=device_id, ts=now, **cols)
                s.add(row)
                s.flush()
                sample = row.to_dict()
        except Exception as e:
            logger.debug("record_metrics_sample failed for %s: %s", device_id, e)
            return None

        try:
            self.evaluate_metric_alerts(device_id, sample)
        except Exception as e:
            logger.debug("evaluate_metric_alerts failed for %s: %s", device_id, e)
        return sample

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    @staticmethod
    def _tier_for_window(window_s):
        """Pick the coarsest tier that still covers ``window_s`` at useful resolution."""
        if window_s <= RAW_RETENTION_S:
            return DeviceMetricRaw, "raw"
        if window_s <= HOURLY_RETENTION_S:
            return DeviceMetricHourly, "hourly"
        return DeviceMetricDaily, "daily"

    @staticmethod
    def _sample_value(row, metric):
        if metric.startswith("extra."):
            return (row.extra or {}).get(metric[6:])
        return getattr(row, metric, None)

    def _query_points(self, session, model, device_id, metric, since):
        rows = (session.query(model)
                .filter(model.device_id == device_id, model.ts >= since)
                .order_by(model.ts.asc())
                .all())
        points = []
        for r in rows:
            v = self._sample_value(r, metric)
            if v is not None:
                points.append({"ts": r.ts, "value": v})
        return points

    def get_device_metrics(self, device_id, metric="battery_pct", period="24h"):
        """Return a time-series for one device+metric over ``period`` from the right tier."""
        device_id = self._resolve_metric_device_id(device_id)
        window = parse_period(period)
        model, tier = self._tier_for_window(window)
        since = time.time() - window
        with session_scope() as s:
            points = self._query_points(s, model, device_id, metric, since)
        return {
            "device_id": device_id,
            "metric": metric,
            "period": period,
            "tier": tier,
            "points": points,
            "count": len(points),
        }

    def get_fleet_metrics(self, metric="battery_pct", device_ids=None, period="24h"):
        """Return aligned per-device series for a metric over ``period`` (comparison charts)."""
        window = parse_period(period)
        model, tier = self._tier_for_window(window)
        since = time.time() - window
        series = []
        with session_scope() as s:
            if not device_ids:
                device_ids = [r[0] for r in
                              s.query(model.device_id).distinct().all()]
            for did in device_ids:
                rid = self._resolve_metric_device_id(did)
                series.append({
                    "device_id": did,
                    "points": self._query_points(s, model, rid, metric, since),
                })
        return {"metric": metric, "period": period, "tier": tier,
                "series": series, "count": len(series)}

    def get_fleet_sparklines(self, metric="battery_pct", device_ids=None, period="24h",
                             max_points=30):
        """Return ``{device_id: [values]}`` downsampled to ``max_points`` for inline
        sparklines on the dashboard (one cheap batch call for the whole fleet)."""
        fleet = self.get_fleet_metrics(metric=metric, device_ids=device_ids, period=period)
        out = {}
        for entry in fleet["series"]:
            values = [p["value"] for p in entry["points"]]
            out[entry["device_id"]] = _downsample(values, max_points)
        return {"metric": metric, "period": period, "sparklines": out}

    def get_device_sparkline(self, device_id, metric="battery_pct", period="24h",
                             max_points=30):
        series = self.get_device_metrics(device_id, metric=metric, period=period)
        return _downsample([p["value"] for p in series["points"]], max_points)

    def _resolve_metric_device_id(self, device_id):
        """Prefer the canonical agent device_id so ADB serials and agent ids line up."""
        if hasattr(self, "_resolve_agent_device_id"):
            try:
                return self._resolve_agent_device_id(device_id)
            except Exception:
                pass
        return device_id

    # ------------------------------------------------------------------
    # Rollup + prune
    # ------------------------------------------------------------------
    @staticmethod
    def _aggregate_bucket(rows):
        """Average the numeric columns over ``rows``; carry the latest categorical values."""
        agg = {}
        for col in METRIC_NUMERIC_COLUMNS:
            vals = [getattr(r, col) for r in rows if getattr(r, col) is not None]
            agg[col] = round(sum(vals) / len(vals), 4) if vals else None
        latest = max(rows, key=lambda r: r.ts)
        agg["network_type"] = latest.network_type
        agg["screen_on"] = latest.screen_on
        # Merge extra keys, averaging numeric ones.
        extra_acc = {}
        for r in rows:
            for k, v in (r.extra or {}).items():
                if isinstance(v, (int, float)):
                    extra_acc.setdefault(k, []).append(v)
        agg["extra"] = {k: round(sum(v) / len(v), 4) for k, v in extra_acc.items()}
        agg["samples"] = len(rows)
        return agg

    def _rollup_tier(self, session, source_model, dest_model, bucket_s):
        """Recompute every bucket present in ``source_model`` into ``dest_model`` (idempotent
        upsert keyed on device_id+bucket-start)."""
        buckets = {}  # (device_id, bucket_start) -> [rows]
        for row in session.query(source_model).all():
            start = int(row.ts // bucket_s) * bucket_s
            buckets.setdefault((row.device_id, float(start)), []).append(row)

        upserts = 0
        for (device_id, start), rows in buckets.items():
            agg = self._aggregate_bucket(rows)
            existing = (session.query(dest_model)
                        .filter(dest_model.device_id == device_id, dest_model.ts == start)
                        .one_or_none())
            if existing is None:
                existing = dest_model(device_id=device_id, ts=start)
                session.add(existing)
            for k, v in agg.items():
                setattr(existing, k, v)
            upserts += 1
        return upserts

    def rollup_metrics(self):
        """Aggregate raw→hourly and hourly→daily. Idempotent; safe to run on a schedule."""
        with session_scope() as s:
            hourly = self._rollup_tier(s, DeviceMetricRaw, DeviceMetricHourly, HOUR_S)
        with session_scope() as s:
            daily = self._rollup_tier(s, DeviceMetricHourly, DeviceMetricDaily, DAY_S)
        return {"hourly_buckets": hourly, "daily_buckets": daily}

    def prune_metrics(self, raw_retention=RAW_RETENTION_S, hourly_retention=HOURLY_RETENTION_S,
                      daily_retention=DAILY_RETENTION_S):
        """Trim each tier to its retention window. Returns per-tier deleted counts."""
        now = time.time()
        removed = {}
        with session_scope() as s:
            removed["raw"] = s.execute(
                delete(DeviceMetricRaw).where(DeviceMetricRaw.ts < now - raw_retention)
            ).rowcount
            removed["hourly"] = s.execute(
                delete(DeviceMetricHourly).where(DeviceMetricHourly.ts < now - hourly_retention)
            ).rowcount
            removed["daily"] = s.execute(
                delete(DeviceMetricDaily).where(DeviceMetricDaily.ts < now - daily_retention)
            ).rowcount
        return removed

    def _job_rollup_metrics(self, job):
        return self.rollup_metrics()

    def _job_prune_metrics(self, job):
        return self.prune_metrics()

    # ------------------------------------------------------------------
    # Threshold alert rules (CRUD)
    # ------------------------------------------------------------------
    def create_metric_alert_rule(self, metric, op, value, event_key, severity=None,
                                 device_id=None, cooldown_seconds=300, enabled=True):
        if op not in MetricAlertRule.OPS:
            raise ValueError(f"Unsupported operator '{op}'")
        with session_scope() as s:
            rule = MetricAlertRule(
                metric=metric, op=op, value=float(value), event_key=event_key,
                severity=severity, device_id=device_id,
                cooldown_seconds=int(cooldown_seconds), enabled=bool(enabled),
                created_at=time.time())
            s.add(rule)
            s.flush()
            return rule.to_dict()

    def list_metric_alert_rules(self, device_id=None):
        with session_scope() as s:
            q = s.query(MetricAlertRule)
            if device_id is not None:
                q = q.filter(MetricAlertRule.device_id == device_id)
            return [r.to_dict() for r in q.order_by(MetricAlertRule.created_at.asc()).all()]

    def get_metric_alert_rule(self, rule_id):
        with session_scope() as s:
            r = s.get(MetricAlertRule, rule_id)
            return r.to_dict() if r else None

    def update_metric_alert_rule(self, rule_id, **fields):
        if "op" in fields and fields["op"] not in MetricAlertRule.OPS:
            raise ValueError(f"Unsupported operator '{fields['op']}'")
        with session_scope() as s:
            r = s.get(MetricAlertRule, rule_id)
            if not r:
                return None
            for key in ("metric", "op", "value", "event_key", "severity", "device_id",
                        "cooldown_seconds", "enabled"):
                if key in fields:
                    setattr(r, key, fields[key])
            return r.to_dict()

    def delete_metric_alert_rule(self, rule_id):
        with session_scope() as s:
            r = s.get(MetricAlertRule, rule_id)
            if not r:
                return False
            s.delete(r)
        return True

    def seed_default_metric_alert_rules(self):
        """Seed a starter rule (battery < 20% → notification) if no rules exist yet."""
        with session_scope() as s:
            if s.query(MetricAlertRule).count() > 0:
                return 0
            s.add(MetricAlertRule(
                metric="battery_pct", op="<", value=20.0,
                event_key="device.battery.low", severity="warning",
                device_id=None, cooldown_seconds=1800, enabled=True,
                created_at=time.time()))
        logger.info("Seeded default metric alert rule (battery_pct < 20)")
        return 1

    # ------------------------------------------------------------------
    # Threshold alert evaluation
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_op(left, op, right):
        if left is None:
            return False
        try:
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op == "=":
                return left == right
            if op == "!=":
                return left != right
        except TypeError:
            return False
        return False

    def evaluate_metric_alerts(self, device_id, sample):
        """Evaluate every enabled rule that applies to this device against the sample and emit
        a notification on a match, honoring each rule's cooldown."""
        rules = [r for r in self.list_metric_alert_rules()
                 if r["enabled"] and (r["device_id"] in (None, device_id))]
        if not rules:
            return []
        now = time.time()
        fired = []
        for rule in rules:
            value = self._sample_metric_value(sample, rule["metric"])
            if not self._apply_op(value, rule["op"], rule["value"]):
                continue
            key = (rule["id"], device_id)
            with self._metric_alert_lock:
                last = self._metric_alert_last_fired.get(key, 0)
                if now - last < (rule.get("cooldown_seconds") or 0):
                    continue
                self._metric_alert_last_fired[key] = now
            self._emit_metric_alert(device_id, rule, value)
            fired.append(rule["id"])
        return fired

    @staticmethod
    def _sample_metric_value(sample, metric):
        if metric.startswith("extra."):
            return (sample.get("extra") or {}).get(metric[6:])
        return sample.get(metric)

    def _emit_metric_alert(self, device_id, rule, value):
        if not hasattr(self, "notify_event"):
            return
        name = device_id
        if hasattr(self, "_agent_device_name"):
            try:
                name = self._agent_device_name(device_id)
            except Exception:
                pass
        data = {
            "device_id": device_id,
            "device_name": name,
            "metric": rule["metric"],
            "value": value,
            "threshold": rule["value"],
            "op": rule["op"],
            # Convenience aliases so the existing catalog templates render.
            "level": value if rule["metric"] == "battery_pct" else None,
        }
        self.notify_event(
            rule["event_key"], data=data, subject_type="device", subject_id=device_id,
            severity=rule.get("severity"))

    # ------------------------------------------------------------------
    # FQL derived fields
    # ------------------------------------------------------------------
    def _register_metric_fql_fields(self):
        if not hasattr(self, "register_fql_field"):
            return
        self.register_fql_field("storage.free_gb", {
            "resolver": self._fql_storage_free_gb,
            "description": "Latest free storage in GB (metrics history)",
        })
        self.register_fql_field("battery.trend_24h", {
            "resolver": self._fql_battery_trend_24h,
            "description": "Battery %% change over the last 24h (negative = draining)",
        })
        self.register_fql_field("metrics.cpu_load_1h_avg", {
            "resolver": self._fql_cpu_load_1h_avg,
            "description": "Average CPU load over the last hour (metrics history)",
        })

    def _latest_sample_value(self, device_id, metric, window_s):
        did = self._resolve_metric_device_id(device_id)
        since = time.time() - window_s
        with session_scope() as s:
            row = (s.query(DeviceMetricRaw)
                   .filter(DeviceMetricRaw.device_id == did, DeviceMetricRaw.ts >= since)
                   .order_by(DeviceMetricRaw.ts.desc())
                   .first())
            return getattr(row, metric, None) if row else None

    def _fql_device_id(self, device):
        return device.get("device_id") or device.get("serial") or ""

    def _fql_storage_free_gb(self, device):
        v = self._latest_sample_value(self._fql_device_id(device), "storage_free", DAY_S)
        return round(v / 1024.0, 2) if v is not None else 0

    def _fql_cpu_load_1h_avg(self, device):
        did = self._resolve_metric_device_id(self._fql_device_id(device))
        since = time.time() - HOUR_S
        with session_scope() as s:
            rows = (s.query(DeviceMetricRaw)
                    .filter(DeviceMetricRaw.device_id == did, DeviceMetricRaw.ts >= since)
                    .all())
        vals = [r.cpu_load for r in rows if r.cpu_load is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0

    def _fql_battery_trend_24h(self, device):
        did = self._resolve_metric_device_id(self._fql_device_id(device))
        since = time.time() - DAY_S
        with session_scope() as s:
            rows = (s.query(DeviceMetricRaw)
                    .filter(DeviceMetricRaw.device_id == did, DeviceMetricRaw.ts >= since)
                    .order_by(DeviceMetricRaw.ts.asc())
                    .all())
        pts = [r.battery_pct for r in rows if r.battery_pct is not None]
        if len(pts) < 2:
            return 0
        return round(pts[-1] - pts[0], 2)


def _downsample(values, max_points):
    """Reduce ``values`` to at most ``max_points`` by even-stride sampling (keeps the last)."""
    n = len(values)
    if n <= max_points or max_points <= 0:
        return list(values)
    step = n / max_points
    out = [values[min(n - 1, int(i * step))] for i in range(max_points)]
    out[-1] = values[-1]
    return out
