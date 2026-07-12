"""Workspace, membership & grant routes (plan 20, part 4).

These self-authorize via the capability fold (``require_member``) rather than the global write
gate, so a workspace owner who is only a *global* operator can still manage their own workspace.
Platform admins bypass every check.
"""
from flask import Blueprint, jsonify, request, g


def make_blueprint(client, limiter):
    bp = Blueprint("workspaces", __name__)

    def _principal():
        return getattr(g, "principal", None) or client.anonymous_principal()

    def _guard(workspace_id, min_role):
        ok, error = client.require_member(_principal(), workspace_id, min_role)
        if not ok:
            body, status = error
            return jsonify(body), status
        return None

    # ---------------------------------------------------------- workspaces
    @bp.route("/workspaces")
    def list_ws():
        p = _principal()
        # Platform admins see every workspace; a user sees the ones they belong to.
        for_user = None if p.is_admin else getattr(p, "user_id", None)
        workspaces = client.list_workspaces(for_user=for_user)
        return jsonify({"workspaces": workspaces, "count": len(workspaces)})

    @bp.route("/workspaces", methods=["POST"])
    def create_ws():
        p = _principal()
        if not p.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        data = request.get_json(silent=True) or {}
        try:
            ws = client.create_workspace(
                name=data.get("name"),
                slug=data.get("slug"),
                created_by=getattr(p, "user_id", None),
                max_devices=data.get("max_devices"),
                max_members=data.get("max_members"),
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"workspace": ws}), 201

    @bp.route("/workspaces/<workspace_id>")
    def get_ws(workspace_id):
        guard = _guard(workspace_id, "viewer")
        if guard:
            return guard
        ws = client.get_workspace(workspace_id)
        if not ws:
            return jsonify({"error": "workspace not found"}), 404
        return jsonify({"workspace": ws})

    @bp.route("/workspaces/<workspace_id>", methods=["PUT"])
    def update_ws(workspace_id):
        guard = _guard(workspace_id, "admin")
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            ws = client.update_workspace(
                workspace_id, name=data.get("name"), status=data.get("status"),
                max_devices=data.get("max_devices"), max_members=data.get("max_members"))
        except ValueError as e:
            code = 404 if str(e) == "workspace not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"workspace": ws})

    @bp.route("/workspaces/<workspace_id>", methods=["DELETE"])
    def delete_ws(workspace_id):
        guard = _guard(workspace_id, "owner")
        if guard:
            return guard
        try:
            client.delete_workspace(workspace_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"ok": True})

    # ---------------------------------------------------------- members
    @bp.route("/workspaces/<workspace_id>/members")
    def list_members(workspace_id):
        guard = _guard(workspace_id, "viewer")
        if guard:
            return guard
        members = client.list_members(workspace_id)
        return jsonify({"members": members, "count": len(members)})

    @bp.route("/workspaces/<workspace_id>/members", methods=["POST"])
    def add_member(workspace_id):
        guard = _guard(workspace_id, "admin")
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            member = client.add_member(workspace_id, data.get("user_id"),
                                       role=data.get("role", "member"))
        except ValueError as e:
            code = 404 if str(e) == "workspace not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"member": member}), 201

    @bp.route("/workspaces/<workspace_id>/members/<user_id>", methods=["PUT"])
    def update_member(workspace_id, user_id):
        guard = _guard(workspace_id, "admin")
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            member = client.update_member(workspace_id, user_id, data.get("role"))
        except ValueError as e:
            code = 404 if str(e) == "member not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"member": member})

    @bp.route("/workspaces/<workspace_id>/members/<user_id>", methods=["DELETE"])
    def remove_member(workspace_id, user_id):
        guard = _guard(workspace_id, "admin")
        if guard:
            return guard
        try:
            client.remove_member(workspace_id, user_id)
        except ValueError as e:
            code = 404 if str(e) == "member not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"ok": True})

    # ---------------------------------------------------------- grants
    @bp.route("/grants")
    def list_grants():
        p = _principal()
        # Admins see all; a user sees grants issued to them.
        user_id = None if p.is_admin else getattr(p, "user_id", None)
        grants = client.list_grants(
            resource_type=request.args.get("resource_type"),
            resource_id=request.args.get("resource_id"),
            user_id=request.args.get("user_id") if p.is_admin else user_id,
        )
        return jsonify({"grants": grants, "count": len(grants)})

    @bp.route("/grants", methods=["POST"])
    def create_grant():
        p = _principal()
        data = request.get_json(silent=True) or {}
        rtype, rid = data.get("resource_type"), data.get("resource_id")
        # Sharing requires platform admin, or admin/owner of the resource's workspace.
        if not p.is_admin:
            wsid = client.resource_workspace_id(rtype, rid)
            ok, error = client.require_member(p, wsid, "admin") if wsid else (False, None)
            if not ok:
                return jsonify({"error": "Insufficient privileges to share this resource"}), 403
        try:
            grant = client.create_grant(rtype, rid, data.get("user_id"),
                                        level=data.get("level", "viewer"),
                                        granted_by=getattr(p, "user_id", None))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"grant": grant}), 201

    @bp.route("/grants/<grant_id>", methods=["DELETE"])
    def revoke_grant(grant_id):
        if not _principal().is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        try:
            client.revoke_grant(grant_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"ok": True})

    return bp
