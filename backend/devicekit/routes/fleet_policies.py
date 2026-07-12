"""Desired-state fleet policy routes (plan 23).

CRUD + validate over ``devicekit.yaml`` policies. Falls under the ``/fleet`` path family, so
the plan-20 write-gate maps these to the ``devices`` feature automatically.
"""
from flask import Blueprint, jsonify, request, g

from devicekit.policy.spec import PolicySpecError


def _workspace_id():
    return getattr(getattr(g, "principal", None), "workspace_id", None)


def _principal_name():
    principal = getattr(g, "principal", None)
    return getattr(principal, "username", None) or getattr(principal, "label", None)


def make_blueprint(client, limiter):
    bp = Blueprint("fleet_policies", __name__)

    @bp.route("/fleet-policies", methods=["GET"])
    def list_policies():
        policies = client.list_fleet_policies(
            workspace_id=_workspace_id(), status=request.args.get("status"))
        return jsonify({"policies": policies, "count": len(policies)})

    @bp.route("/fleet-policies", methods=["POST"])
    def create_policy():
        data = request.get_json(silent=True) or {}
        yaml_text = data.get("yaml") or ""
        try:
            policy = client.create_fleet_policy(
                yaml_text,
                name=data.get("name"),
                auto_apply=data.get("autoApply", data.get("auto_apply")),
                source=data.get("source"),
                workspace_id=_workspace_id(),
                created_by=_principal_name(),
            )
        except PolicySpecError as e:
            return jsonify({"error": "invalid policy", "errors": e.errors}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"policy": policy}), 201

    @bp.route("/fleet-policies/validate", methods=["POST"])
    def validate_policy():
        data = request.get_json(silent=True) or {}
        return jsonify(client.validate_fleet_policy_yaml(data.get("yaml") or ""))

    @bp.route("/fleet-policies/scaffold", methods=["POST"])
    def scaffold_policy():
        """Render a devicekit.yaml from a live device's current state (adopt-then-edit).
        Pass ``save: true`` to persist it as a pending policy in one call."""
        data = request.get_json(silent=True) or {}
        device_id = data.get("device_id") or data.get("deviceId")
        if not device_id:
            return jsonify({"error": "device_id is required"}), 400
        try:
            result = client.scaffold_fleet_policy(device_id, name=data.get("name"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        if data.get("save"):
            policy = client.create_fleet_policy(
                result["yaml"], name=data.get("name"),
                workspace_id=_workspace_id(), created_by=_principal_name())
            return jsonify({**result, "policy": policy}), 201
        return jsonify(result)

    @bp.route("/fleet-policies/<policy_id>/plan", methods=["GET"])
    def plan_policy(policy_id):
        """Dry-run diff: ordered steps + issues + hard blockers. Never mutates."""
        try:
            plan = client.plan_fleet_policy(policy_id)
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return jsonify({"error": str(e)}), status
        return jsonify({"plan": plan})

    @bp.route("/fleet-policies/<policy_id>/apply", methods=["POST"])
    def apply_policy(policy_id):
        """Apply the stored policy. Blockers refuse with 409 (no --force); an unchanged
        hash or already-converged fleet short-circuits without a job."""
        try:
            result = client.apply_fleet_policy(policy_id, triggered_by="manual")
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return jsonify({"error": str(e)}), status
        if result.get("refused"):
            return jsonify({"error": "plan has blockers; apply refused",
                            "blockers": result["plan"]["blockers"],
                            "plan": result["plan"]}), 409
        status = 202 if result.get("job") else 200
        return jsonify(result), status

    @bp.route("/fleet-policies/<policy_id>/check-drift", methods=["POST"])
    def check_drift(policy_id):
        """One-shot drift evaluation (the scheduled job does this periodically)."""
        try:
            result = client.check_fleet_policy_drift(policy_id)
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return jsonify({"error": str(e)}), status
        return jsonify(result)

    @bp.route("/fleet-policies/<policy_id>/reconcile", methods=["POST"])
    def reconcile_policy(policy_id):
        """Reconcile = apply the stored spec to a drifted fleet. Pending-by-default:
        nothing reconciles unless an operator calls this (or the policy opts into
        autoApply). Same refusal semantics as apply."""
        try:
            result = client.apply_fleet_policy(policy_id, triggered_by="reconcile")
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return jsonify({"error": str(e)}), status
        if result.get("refused"):
            return jsonify({"error": "plan has blockers; reconcile refused",
                            "blockers": result["plan"]["blockers"],
                            "plan": result["plan"]}), 409
        status = 202 if result.get("job") else 200
        return jsonify(result), status

    @bp.route("/fleet-policies/<policy_id>", methods=["GET"])
    def get_policy(policy_id):
        policy = client.get_fleet_policy(policy_id)
        if not policy:
            return jsonify({"error": "policy not found"}), 404
        return jsonify({"policy": policy})

    @bp.route("/fleet-policies/<policy_id>", methods=["PUT"])
    def update_policy(policy_id):
        data = request.get_json(silent=True) or {}
        try:
            policy = client.update_fleet_policy(
                policy_id,
                yaml_text=data.get("yaml"),
                name=data.get("name"),
                auto_apply=data.get("autoApply", data.get("auto_apply")),
                source=data.get("source"),
            )
        except PolicySpecError as e:
            return jsonify({"error": "invalid policy", "errors": e.errors}), 400
        except ValueError as e:
            status = 404 if "not found" in str(e) else 400
            return jsonify({"error": str(e)}), status
        return jsonify({"policy": policy})

    @bp.route("/fleet-policies/<policy_id>", methods=["DELETE"])
    def delete_policy(policy_id):
        try:
            client.delete_fleet_policy(policy_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"deleted": True})

    return bp
