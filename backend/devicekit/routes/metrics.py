"""Metrics history + threshold alert rule routes (plan 08).

Period queries pick the right rollup tier transparently (``?period=1h|24h|7d|30d``):

* ``GET /devices/<id>/metrics?metric=battery_pct&period=7d`` — one device's series.
* ``GET /fleet/metrics?metric=...&devices=a,b&period=24h`` — aligned multi-device series.
* ``GET /fleet/metrics/sparklines?metric=...&period=24h`` — downsampled per-device values.
* ``GET|POST|PUT|DELETE /metrics/alert-rules`` — threshold rules feeding the notification bus.

List envelopes follow the house convention (``{'<resource>': [...], 'count': N}``); errors
are ``{'error': msg}, status``.
"""
from flask import Blueprint, jsonify, request

from devicekit.mixins.metrics_history import QUERYABLE_METRICS
from devicekit.models.metric_alert import MetricAlertRule
from devicekit.services.scopes import require_scope


def make_blueprint(client, limiter):
    bp = Blueprint('metrics', __name__)

    def _valid_metric(metric):
        return metric in QUERYABLE_METRICS or (metric or '').startswith('extra.')

    @bp.route('/devices/<device_id>/metrics')
    @require_scope('metrics:read')
    def device_metrics(device_id):
        metric = request.args.get('metric', 'battery_pct')
        period = request.args.get('period', '24h')
        if not _valid_metric(metric):
            return jsonify({'error': f'Unknown metric: {metric}'}), 400
        return jsonify(client.get_device_metrics(device_id, metric=metric, period=period))

    @bp.route('/devices/<device_id>/metrics/sparkline')
    @require_scope('metrics:read')
    def device_metrics_sparkline(device_id):
        metric = request.args.get('metric', 'battery_pct')
        period = request.args.get('period', '24h')
        if not _valid_metric(metric):
            return jsonify({'error': f'Unknown metric: {metric}'}), 400
        values = client.get_device_sparkline(device_id, metric=metric, period=period)
        return jsonify({'device_id': device_id, 'metric': metric, 'values': values})

    @bp.route('/fleet/metrics')
    @require_scope('metrics:read')
    def fleet_metrics():
        metric = request.args.get('metric', 'battery_pct')
        period = request.args.get('period', '24h')
        devices = request.args.get('devices')
        device_ids = [d for d in devices.split(',') if d] if devices else None
        if not _valid_metric(metric):
            return jsonify({'error': f'Unknown metric: {metric}'}), 400
        return jsonify(client.get_fleet_metrics(
            metric=metric, device_ids=device_ids, period=period))

    @bp.route('/fleet/metrics/sparklines')
    @require_scope('metrics:read')
    def fleet_sparklines():
        metric = request.args.get('metric', 'battery_pct')
        period = request.args.get('period', '24h')
        devices = request.args.get('devices')
        device_ids = [d for d in devices.split(',') if d] if devices else None
        if not _valid_metric(metric):
            return jsonify({'error': f'Unknown metric: {metric}'}), 400
        return jsonify(client.get_fleet_sparklines(
            metric=metric, device_ids=device_ids, period=period))

    @bp.route('/metrics/catalog')
    @require_scope('metrics:read')
    def metrics_catalog():
        """Discoverable list of queryable metrics for the UI selectors."""
        return jsonify({'metrics': sorted(QUERYABLE_METRICS)})

    # ── Threshold alert rules ──
    @bp.route('/metrics/alert-rules')
    @require_scope('metrics:read')
    def alert_rules_list():
        device_id = request.args.get('device_id')
        rules = client.list_metric_alert_rules(device_id=device_id)
        return jsonify({'rules': rules, 'count': len(rules)})

    @bp.route('/metrics/alert-rules', methods=['POST'])
    @require_scope('metrics:write')
    def alert_rules_create():
        data = request.get_json(silent=True) or {}
        for field in ('metric', 'op', 'value', 'event_key'):
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        try:
            rule = client.create_metric_alert_rule(
                metric=data['metric'], op=data['op'], value=data['value'],
                event_key=data['event_key'], severity=data.get('severity'),
                device_id=data.get('device_id'),
                cooldown_seconds=data.get('cooldown_seconds', 300),
                enabled=data.get('enabled', True))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(rule), 201

    @bp.route('/metrics/alert-rules/<rule_id>', methods=['PUT'])
    @require_scope('metrics:write')
    def alert_rules_update(rule_id):
        data = request.get_json(silent=True) or {}
        try:
            rule = client.update_metric_alert_rule(rule_id, **data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        if rule is None:
            return jsonify({'error': 'Rule not found'}), 404
        return jsonify(rule)

    @bp.route('/metrics/alert-rules/<rule_id>', methods=['DELETE'])
    @require_scope('metrics:write')
    def alert_rules_delete(rule_id):
        if not client.delete_metric_alert_rule(rule_id):
            return jsonify({'error': 'Rule not found'}), 404
        return jsonify({'status': 'deleted'})

    @bp.route('/metrics/alert-rules/ops')
    @require_scope('metrics:read')
    def alert_rules_ops():
        return jsonify({'ops': list(MetricAlertRule.OPS)})

    return bp
