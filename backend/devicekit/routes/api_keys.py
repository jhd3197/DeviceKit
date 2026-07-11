"""API-key management routes (plan 20, part 2).

Admin-only. ``POST /api-keys`` returns the raw ``dk_`` key **once** (never retrievable again);
list/get show only the display prefix + status. The write gate maps ``/api-keys`` to the
``settings`` feature (admin-write), and these handlers additionally require admin for reads so a
non-admin can't enumerate keys.
"""
from flask import Blueprint, jsonify, request, g


def make_blueprint(client, limiter):
    bp = Blueprint("api_keys", __name__)

    def _require_admin():
        principal = getattr(g, "principal", None) or client.anonymous_principal()
        if not principal.is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return None

    @bp.route("/api-keys")
    def list_keys():
        guard = _require_admin()
        if guard:
            return guard
        keys = client.list_api_keys()
        return jsonify({"api_keys": keys, "count": len(keys)})

    @bp.route("/api-keys/scopes")
    def scopes_catalog():
        guard = _require_admin()
        if guard:
            return guard
        return jsonify({"scopes": client.api_key_scopes_catalog()})

    @bp.route("/api-keys", methods=["POST"])
    def create_key():
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        principal = getattr(g, "principal", None)
        try:
            key = client.create_api_key(
                name=data.get("name"),
                scopes=data.get("scopes"),
                created_by=getattr(principal, "user_id", None),
                expires_in_days=data.get("expires_in_days"),
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"api_key": key}), 201

    @bp.route("/api-keys/<key_id>")
    def get_key(key_id):
        guard = _require_admin()
        if guard:
            return guard
        key = client.get_api_key(key_id)
        if not key:
            return jsonify({"error": "api key not found"}), 404
        return jsonify({"api_key": key})

    @bp.route("/api-keys/<key_id>", methods=["DELETE"])
    def revoke_key(key_id):
        guard = _require_admin()
        if guard:
            return guard
        try:
            key = client.revoke_api_key(key_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"api_key": key})

    @bp.route("/api-keys/<key_id>/rotate", methods=["POST"])
    def rotate_key(key_id):
        guard = _require_admin()
        if guard:
            return guard
        try:
            key = client.rotate_api_key(key_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"api_key": key})

    return bp
