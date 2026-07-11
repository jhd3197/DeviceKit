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
        result = client.authenticate(
            data.get("username", ""),
            data.get("password", ""),
            code=data.get("code"),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        if result.get("ok"):
            return jsonify({"token": result["token"], "user": result["user"],
                            "must_enroll_2fa": result.get("must_enroll_2fa", False)})
        if result.get("locked"):
            return jsonify({"error": result["error"],
                            "retry_after": result.get("retry_after")}), 429
        if result.get("mfa_required"):
            # Password OK (or a bad 2FA code): prompt for the authenticator code.
            return jsonify({"mfa_required": True,
                            "error": result.get("error")}), 401
        return jsonify({"error": result.get("error", "Invalid credentials")}), 401

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
        body = {
            "authenticated": authenticated,
            "login_required": login_required,
            "has_users": client.has_users(),
            "principal": principal.to_dict() if authenticated else None,
        }
        # Surface the require-2FA policy status for a logged-in user (if the mixin is present).
        if authenticated and getattr(principal, "user_id", None) and hasattr(client, "twofa_policy_status"):
            user = client.get_user(principal.user_id)
            if user:
                body["twofa"] = client.twofa_policy_status(user)
        return jsonify(body)

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

    # -------------------------------------------------------------
    # TOTP 2FA (self-service — the logged-in user manages their own)
    # -------------------------------------------------------------
    def _require_user():
        uid = getattr(_principal(), "user_id", None)
        if not uid:
            return None, (jsonify({"error": "A logged-in user is required"}), 403)
        return uid, None

    @bp.route("/auth/2fa/setup", methods=["POST"])
    def totp_setup():
        uid, err = _require_user()
        if err:
            return err
        return jsonify(client.start_totp_enrollment(uid))

    @bp.route("/auth/2fa/confirm", methods=["POST"])
    def totp_confirm():
        uid, err = _require_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        try:
            result = client.confirm_totp(uid, data.get("code"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(result)

    @bp.route("/auth/2fa/disable", methods=["POST"])
    def totp_disable():
        uid, err = _require_user()
        if err:
            return err
        client.disable_totp(uid)
        return jsonify({"ok": True})

    # -------------------------------------------------------------
    # Invitations (admin manage; preview + accept are public)
    # -------------------------------------------------------------
    @bp.route("/invitations")
    def invitations_list():
        guard = _require_admin()
        if guard:
            return guard
        invites = client.list_invitations()
        return jsonify({"invitations": invites, "count": len(invites)})

    @bp.route("/invitations", methods=["POST"])
    def invitations_create():
        guard = _require_admin()
        if guard:
            return guard
        data = request.get_json(silent=True) or {}
        try:
            inv = client.create_invitation(
                role=data.get("role", "viewer"), email=data.get("email"),
                permissions=data.get("permissions"), workspace_id=data.get("workspace_id"),
                workspace_role=data.get("workspace_role"),
                invited_by=getattr(_principal(), "user_id", None),
                expires_in_days=data.get("expires_in_days", 7))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"invitation": inv}), 201

    @bp.route("/invitations/<invitation_id>", methods=["DELETE"])
    def invitations_revoke(invitation_id):
        guard = _require_admin()
        if guard:
            return guard
        try:
            client.revoke_invitation(invitation_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"ok": True})

    @bp.route("/invitations/<token>/preview")
    def invitations_preview(token):
        preview = client.get_invitation_preview(token)
        if not preview:
            return jsonify({"error": "invitation is not valid"}), 404
        return jsonify({"invitation": preview})

    @bp.route("/invitations/<token>/accept", methods=["POST"])
    def invitations_accept(token):
        data = request.get_json(silent=True) or {}
        try:
            user = client.accept_invitation(token, data.get("username"), data.get("password"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"user": user}), 201

    return bp
