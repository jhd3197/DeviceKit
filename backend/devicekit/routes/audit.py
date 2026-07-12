"""Audit-trail routes (plan 20, part 3). Admin-only read of the durable, attributed log."""
from flask import Blueprint, jsonify, request, g


def make_blueprint(client, limiter):
    bp = Blueprint("audit", __name__)

    def _require_admin():
        principal = getattr(g, "principal", None) or client.anonymous_principal()
        if not principal.is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return None

    @bp.route("/audit")
    def audit_list():
        guard = _require_admin()
        if guard:
            return guard
        logs = client.get_audit_logs(
            limit=request.args.get("limit", 100),
            user_id=request.args.get("user_id"),
            action=request.args.get("action"),
            target_type=request.args.get("target_type"),
            target_id=request.args.get("target_id"),
            since=request.args.get("since"),
        )
        return jsonify({"audit_log": logs, "count": len(logs)})

    return bp
