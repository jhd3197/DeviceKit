"""Secrets-vault routes (plan 20, part 5).

Admin-gated (``/vault`` maps to the ``settings`` feature in the write gate, and reads self-check
admin). Values are masked on list; ``.../reveal`` is the separate decryption path so a plaintext
read is a distinct, auditable action. Vault listing narrows to the active workspace.
"""
from flask import Blueprint, jsonify, request, g


def _workspace_id():
    return getattr(getattr(g, "principal", None), "workspace_id", None)


def make_blueprint(client, limiter):
    bp = Blueprint("vault", __name__)

    def _require_admin():
        principal = getattr(g, "principal", None) or client.anonymous_principal()
        if not principal.is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return None

    def _principal():
        return getattr(g, "principal", None)

    # ---------------------------------------------------------- vaults
    @bp.route("/vault/vaults")
    def list_vaults():
        guard = _require_admin()
        if guard:
            return guard
        vaults = client.list_vaults(workspace_id=_workspace_id())
        return jsonify({"vaults": vaults, "count": len(vaults)})

    @bp.route("/vault/vaults", methods=["POST"])
    def create_vault():
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            vault = client.create_vault(
                name=data.get("name"), slug=data.get("slug"),
                description=data.get("description", ""),
                workspace_id=_workspace_id(),
                created_by=getattr(_principal(), "user_id", None))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"vault": vault}), 201

    @bp.route("/vault/vaults/<vault_id>")
    def get_vault(vault_id):
        guard = _require_admin()
        if guard:
            return guard
        vault = client.get_vault(vault_id)
        if not vault:
            return jsonify({"error": "vault not found"}), 404
        return jsonify({"vault": vault})

    @bp.route("/vault/vaults/<vault_id>", methods=["DELETE"])
    def delete_vault(vault_id):
        guard = _require_admin()
        if guard:
            return guard
        try:
            client.delete_vault(vault_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"ok": True})

    # ---------------------------------------------------------- secrets
    @bp.route("/vault/vaults/<vault_id>/secrets")
    def list_secrets(vault_id):
        guard = _require_admin()
        if guard:
            return guard
        secrets = client.list_secrets(vault_id)
        return jsonify({"secrets": secrets, "count": len(secrets)})

    @bp.route("/vault/vaults/<vault_id>/secrets", methods=["POST"])
    def set_secret(vault_id):
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            secret = client.set_secret(
                vault_id, data.get("key"), data.get("value"),
                description=data.get("description", ""),
                expires_at=data.get("expires_at"),
                created_by=getattr(_principal(), "user_id", None))
        except ValueError as e:
            code = 404 if str(e) == "vault not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"secret": secret}), 201

    @bp.route("/vault/vaults/<vault_id>/secrets/<key>/reveal", methods=["POST"])
    def reveal_secret(vault_id, key):
        guard = _require_admin()
        if guard:
            return guard
        try:
            secret = client.reveal_secret(vault_id, key)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"secret": secret})

    @bp.route("/vault/vaults/<vault_id>/secrets/<key>", methods=["DELETE"])
    def delete_secret(vault_id, key):
        guard = _require_admin()
        if guard:
            return guard
        try:
            client.delete_secret(vault_id, key)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"ok": True})

    return bp
