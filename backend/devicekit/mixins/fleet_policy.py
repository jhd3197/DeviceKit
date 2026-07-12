"""FleetPolicyMixin — desired-state fleet policies (plan 23).

Owns the ``FleetPolicy`` lifecycle: CRUD over validated ``devicekit.yaml`` documents
(part 2), the desired-vs-live plan (part 3), apply-as-a-job (part 4), periodic drift
detection + reconcile (part 5), and scaffolding YAML from a live device (part 6).

Pure logic (spec/planner/scaffold) lives in ``devicekit/policy/``; this mixin supplies the
live-state seams: merged device list (FQL mixin), plan-18 app-driver provisioning, plan-22
schedules, ADB settings, the extension registry, and the plan-20 vault for ``fromSecret``.
"""
import logging
import time
import uuid

from devicekit.db import session_scope
from devicekit.models.fleet_policy import (
    FleetPolicy, STATUS_PENDING, STATUS_APPLIED, STATUS_DRIFTED, STATUS_ERROR)
from devicekit.policy.spec import load_policy, policy_hash
from devicekit.services.workspace import scope_query

logger = logging.getLogger(__name__)


class FleetPolicyMixin:
    """Desired-state policies: declare what a device/group should look like; DeviceKit
    plans the diff, applies it as a job, and watches for drift."""

    # ------------------------------------------------------------------
    # CRUD (part 2)
    # ------------------------------------------------------------------
    def create_fleet_policy(self, yaml_text, name=None, auto_apply=None, source=None,
                            workspace_id=None, created_by=None):
        """Validate + normalize + persist a policy. Raises ``PolicySpecError`` on a bad
        spec, ``ValueError`` on anything else."""
        spec = load_policy(yaml_text)
        target_kind = next(iter(spec["target"]))
        policy = FleetPolicy(
            id=str(uuid.uuid4()),
            name=(name or spec.get("name") or "").strip() or f"policy-{target_kind}",
            target_kind=target_kind,
            target_value=spec["target"][target_kind],
            raw_yaml=yaml_text,
            normalized=spec,
            policy_hash=policy_hash(spec),
            status=STATUS_PENDING,
            auto_apply=spec["autoApply"] if auto_apply is None else bool(auto_apply),
            source=source,
            created_by=created_by,
            workspace_id=workspace_id,
            created_at=time.time(),
        )
        with session_scope() as s:
            s.add(policy)
            s.flush()
            out = policy.to_dict(include_spec=True)
        self._broadcast_policy("created", out)
        return out

    def list_fleet_policies(self, workspace_id=None, status=None):
        with session_scope() as s:
            q = scope_query(s.query(FleetPolicy), FleetPolicy, workspace_id)
            if status:
                q = q.filter(FleetPolicy.status == status)
            return [p.to_dict() for p in q.order_by(FleetPolicy.created_at.asc()).all()]

    def get_fleet_policy(self, policy_id, include_spec=True):
        with session_scope() as s:
            p = s.get(FleetPolicy, policy_id)
            return p.to_dict(include_spec=include_spec) if p else None

    def update_fleet_policy(self, policy_id, yaml_text=None, name=None, auto_apply=None,
                            source=None):
        """Re-validate on YAML change; a changed hash flips the policy back to ``pending``
        (the stored applied_hash keeps drift/idempotence honest)."""
        with session_scope() as s:
            p = s.get(FleetPolicy, policy_id)
            if not p:
                raise ValueError("policy not found")
            if yaml_text is not None:
                spec = load_policy(yaml_text)
                new_hash = policy_hash(spec)
                target_kind = next(iter(spec["target"]))
                p.raw_yaml = yaml_text
                p.normalized = spec
                p.target_kind = target_kind
                p.target_value = spec["target"][target_kind]
                if auto_apply is None:
                    p.auto_apply = spec["autoApply"]
                if new_hash != p.policy_hash:
                    p.policy_hash = new_hash
                    p.status = STATUS_PENDING
                    p.status_detail = None
            if name is not None:
                p.name = name.strip()
            if auto_apply is not None:
                p.auto_apply = bool(auto_apply)
            if source is not None:
                p.source = source
            p.updated_at = time.time()
            s.flush()
            out = p.to_dict(include_spec=True)
        self._broadcast_policy("updated", out)
        return out

    def delete_fleet_policy(self, policy_id):
        with session_scope() as s:
            p = s.get(FleetPolicy, policy_id)
            if not p:
                raise ValueError("policy not found")
            out = p.to_dict()
            s.delete(p)
        self._broadcast_policy("deleted", out)
        return True

    def validate_fleet_policy_yaml(self, yaml_text):
        """Dry validation for editors — never persists."""
        from devicekit.policy.spec import PolicySpecError
        try:
            spec = load_policy(yaml_text)
        except PolicySpecError as e:
            return {"valid": False, "errors": e.errors}
        return {"valid": True, "errors": [], "normalized": spec,
                "policy_hash": policy_hash(spec)}

    # ------------------------------------------------------------------
    # Shared internals
    # ------------------------------------------------------------------
    def _set_policy_status(self, policy_id, status, detail=None, applied_hash=None):
        """Single funnel for lifecycle transitions; broadcasts so views update live."""
        now = time.time()
        with session_scope() as s:
            p = s.get(FleetPolicy, policy_id)
            if not p:
                return None
            p.status = status
            p.status_detail = detail
            p.updated_at = now
            if status == STATUS_APPLIED:
                p.applied_at = now
                p.applied_hash = applied_hash or p.policy_hash
            if status in (STATUS_APPLIED, STATUS_DRIFTED):
                p.last_checked_at = now
            s.flush()
            out = p.to_dict()
        self._broadcast_policy("status", out)
        return out

    def _broadcast_policy(self, event, policy_dict):
        try:
            self.broadcast("policy", {"event": event, "policy": {
                k: v for k, v in policy_dict.items() if k not in ("raw_yaml", "normalized")}})
        except Exception:
            pass
