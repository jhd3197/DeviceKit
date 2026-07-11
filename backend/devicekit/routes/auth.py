"""Authentication + user-management routes (plan 20, part 1).

* ``/auth/login`` / ``/auth/logout`` / ``/auth/session`` — the login lifecycle. ``/auth/session``
  is the endpoint the SPA polls on boot to decide *login screen vs straight in* (solo mode
  reports ``authenticated: true`` with no token).
* ``/users`` CRUD — admin-only account management with the global role + narrow-only permission
  override.

The write gate in ``api_app`` already blocks non-admins from mutating ``/users`` (it maps to the
``settings`` feature, which only admins can write); these handlers additionally require admin for
*reads* so the roster isn't visible to operators/viewers.
"""
from flask import Blueprint, jsonify, request, g


def make_blueprint(client, limiter):
    bp = Blueprint("auth", __name__)

    def _principal():
        return getattr(g, "principal", None) or client.anonymous_principal()

    def _require_admin():
        if not _principal().is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return None

    # -------------------------------------------------------------
    # Login lifecycle
    # -------------------------------------------------------------
    @bp.route("/auth/login", methods=["POST"])
    @limiter.limit("10 per minute")
    def login():
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        user = client.verify_credentials(username, password)
        if not user:
            return jsonify({"error": "Invalid credentials"}), 401
        token = client.create_session(
            user["id"],
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        return jsonify({"token": token, "user": user})

    @bp.route("/auth/logout", methods=["POST"])
    def logout():
        token = client._session_token_from(request)
        client.delete_session(token)
        return jsonify({"ok": True})

    @bp.route("/auth/session")
    def session():
        # Resolve directly (this path is public, so the gate left an anonymous principal on g).
        principal = client.resolve_principal(request)
        authenticated = principal is not None and principal.is_authenticated
        login_required = (not authenticated) and (client.has_users() or bool(client._api_key))
        return jsonify({
            "authenticated": authenticated,
            "login_required": login_required,
            "has_users": client.has_users(),
            "principal": principal.to_dict() if authenticated else None,
        })

    @bp.route("/auth/permissions/schema")
    def permissions_schema():
        return jsonify(client.permission_schema())

    # -------------------------------------------------------------
    # User management (admin only)
    # -------------------------------------------------------------
    @bp.route("/users")
    def users_list():
        guard = _require_admin()
        if guard:
            return guard
        users = client.list_users()
        return jsonify({"users": users, "count": len(users)})

    @bp.route("/users", methods=["POST"])
    def users_create():
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            user = client.create_user(
                username=data.get("username"),
                password=data.get("password"),
                role=data.get("role", "viewer"),
                email=data.get("email"),
                permissions=data.get("permissions"),
                is_active=data.get("is_active", True),
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"user": user}), 201

    @bp.route("/users/<user_id>")
    def users_get(user_id):
        guard = _require_admin()
        if guard:
            return guard
        user = client.get_user(user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404
        return jsonify({"user": user})

    @bp.route("/users/<user_id>", methods=["PUT"])
    def users_update(user_id):
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            user = client.update_user(
                user_id,
                role=data.get("role"),
                email=data.get("email"),
                permissions=data.get("permissions"),
                is_active=data.get("is_active"),
                password=data.get("password"),
            )
        except ValueError as e:
            code = 404 if str(e) == "user not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"user": user})

    @bp.route("/users/<user_id>", methods=["DELETE"])
    def users_delete(user_id):
        guard = _require_admin()
        if guard:
            return guard
        try:
            client.delete_user(user_id)
        except ValueError as e:
            code = 404 if str(e) == "user not found" else 400
            return jsonify({"error": str(e)}), code
        return jsonify({"ok": True})

    return bp
