"""FleetPolicyMixin — desired-state fleet policies (plan 23).

Owns the ``FleetPolicy`` lifecycle: CRUD over validated ``devicekit.yaml`` documents
(part 2), the desired-vs-live plan (part 3), apply-as-a-job (part 4), periodic drift
detection + reconcile (part 5), and scaffolding YAML from a live device (part 6).

Pure logic (spec/planner/scaffold) lives in ``devicekit/policy/``; this mixin supplies the
live-state seams: merged device list (FQL mixin), plan-18 app-driver provisioning, plan-22
schedules, ADB settings, the extension registry, and the plan-20 vault for ``fromSecret``.
"""
import logging
import re
import time
import uuid

from devicekit.db import session_scope
from devicekit.models.fleet_policy import (
    FleetPolicy, STATUS_PENDING, STATUS_APPLIED, STATUS_DRIFTED, STATUS_ERROR)
from devicekit.policy.planner import plan_policy, secret_ref_key
from devicekit.policy.spec import effective_spec_for_device, load_policy, policy_hash
from devicekit.services.workspace import scope_query

_VERSION_NAME_RE = re.compile(r"versionName=(\S+)")

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
    # Plan (part 3): resolve targets, snapshot live state, pure diff
    # ------------------------------------------------------------------
    def plan_fleet_policy(self, policy_id):
        """Dry-run diff of desired-vs-live for every targeted device. Never mutates."""
        policy = self.get_fleet_policy(policy_id)
        if not policy:
            raise ValueError("policy not found")
        spec = policy["normalized"]
        device_ids, index = self._resolve_policy_devices(
            policy["target_kind"], policy["target_value"])
        live = self._collect_policy_live_state(spec, device_ids, index)
        plan = plan_policy(spec, device_ids, live)
        plan["policy_id"] = policy_id
        plan["policy_hash"] = policy["policy_hash"]
        return plan

    def _resolve_policy_devices(self, target_kind, target_value):
        """Resolve a policy target to (device_ids, {id: merged device dict}). All three
        target kinds converge on the same canonical id the fleet views use."""
        devices = self.all_devices_for_query()
        index = {}
        for d in devices:
            if d:
                index[d.get("device_id") or d.get("serial")] = d
        if target_kind == "device":
            ids = [target_value]
        elif target_kind == "group":
            group = self.get_device_group(target_value)
            if not group:
                raise ValueError(f"device group not found: {target_value}")
            ids = list(group.get("device_ids") or [])
        elif target_kind == "fql":
            matched = self.execute_fleet_query(target_value, devices=devices)
            ids = [d.get("device_id") or d.get("serial") for d in matched]
        else:
            raise ValueError(f"unknown target kind: {target_kind}")
        return ids, index

    def _collect_policy_live_state(self, spec, device_ids, device_index):
        """Snapshot everything the planner diffs against: per-device installed apps +
        settings (ADB), schedules, extension states, and resolved secret refs."""
        live = {"devices": {}, "app_meta": {}, "extensions": {}, "secrets": {}}
        self._collect_extension_meta(spec, device_ids, live)
        self._collect_secret_refs(spec, live)
        for did in device_ids:
            d = device_index.get(did)
            if not d:
                live["devices"][did] = {"present": False}
                continue
            adb = d.get("source") != "agent"
            online = bool(d.get("online"))
            entry = {"present": True, "online": online, "adb": adb,
                     "apps": {}, "settings": {}, "automations": {}}
            eff = effective_spec_for_device(spec, did)
            if online and adb:
                for app in eff["apps"]:
                    entry["apps"][app["package"]] = self._adb_installed_version(
                        did, app["package"])
                for ns, kv in eff["settings"].items():
                    entry["settings"][ns] = {
                        key: self._adb_get_setting(did, ns, key) for key in kv}
            for auto in eff["automations"]:
                entry["automations"][auto["automation"]] = \
                    self._automation_live_state(auto["automation"], did)
            live["devices"][did] = entry
        return live

    def _collect_extension_meta(self, spec, device_ids, live):
        slugs = set(spec.get("extensions") or [])
        specs = [spec] + [effective_spec_for_device(spec, did) for did in device_ids]
        for eff in specs:
            slugs |= set(eff.get("extensions") or [])
            slugs |= {a["extension"] for a in eff.get("apps") or [] if a.get("extension")}
        registry_index = None
        for slug in slugs:
            ext = self.get_extension(slug) if hasattr(self, "get_extension") else None
            installed = ext is not None
            active = installed and ext.get("status") == "active"
            requirements = (ext or {}).get("manifest", {}).get("device_requirements") or {}
            config = (self.get_extension_config_raw(slug)
                      if installed and hasattr(self, "get_extension_config_raw") else {})
            live["app_meta"][slug] = {
                "installed": installed,
                "active": active,
                "supported_versions": requirements.get("supported_versions"),
                "provision": requirements.get("provision"),
                "apk_supplied": bool(config.get("apk_b64")),
                "apk_version": config.get("apk_version"),
            }
            available = True if installed else None
            if not installed and hasattr(self, "get_extension_registry"):
                if registry_index is None:
                    try:
                        registry = self.get_extension_registry(force=False)
                        registry_index = {e.get("slug") for e in registry or []}
                    except Exception as e:
                        logger.warning(f"Extension registry unavailable at plan time: {e}")
                        registry_index = False  # unreachable — leave availability unknown
                if registry_index is not False:
                    available = slug in registry_index
            live["extensions"][slug] = {
                "installed": installed, "active": active, "available": available}

    def _collect_secret_refs(self, spec, live):
        sections = [spec.get("settings") or {}]
        sections += [(o.get("settings") or {}) for o in (spec.get("overrides") or {}).values()]
        for settings in sections:
            for kv in settings.values():
                for desired in kv.values():
                    if not (isinstance(desired, dict) and desired.get("fromSecret")):
                        continue
                    ref = desired["fromSecret"]
                    key = secret_ref_key(ref)
                    if key in live["secrets"]:
                        continue
                    try:
                        value = self._resolve_secret_ref(ref)
                        live["secrets"][key] = {"found": True, "value": value}
                    except ValueError:
                        live["secrets"][key] = {"found": False, "value": None}

    def _resolve_secret_ref(self, ref):
        """``fromSecret: {vault, key}`` — vault accepted by id or slug. Raises ValueError
        when either half is missing."""
        vault_ref, key = ref["vault"], ref["key"]
        vault_id = None
        for v in self.list_vaults():
            if vault_ref in (v.get("id"), v.get("slug")):
                vault_id = v["id"]
                break
        if not vault_id:
            raise ValueError(f"vault not found: {vault_ref}")
        return self.reveal_secret(vault_id, key)["value"]

    def _automation_live_state(self, ref, device_id):
        automation = self._resolve_automation_ref(ref)
        if not automation:
            return {"automation_id": None}
        schedule = None
        for sch in self.list_schedules(automation["id"]):
            if sch.get("device_id") == device_id:
                schedule = {"id": sch["id"],
                            "interval_minutes": sch.get("interval_minutes"),
                            "enabled": bool(sch.get("enabled"))}
                break
        return {"automation_id": automation["id"], "name": automation.get("name"),
                "schedule": schedule}

    def _resolve_automation_ref(self, ref):
        automation = self.get_automation(ref)
        if automation:
            return automation
        for a in self.list_automations():
            if a.get("name") == ref:
                return a
        return None

    def _adb_installed_version(self, device_id, package):
        out = self.run_adb_command(["shell", "dumpsys", "package", package],
                                   device=device_id) or ""
        m = _VERSION_NAME_RE.search(out)
        return m.group(1) if m else None

    def _adb_get_setting(self, device_id, namespace, key):
        out = self.run_adb_command(["shell", "settings", "get", namespace, key],
                                   device=device_id)
        out = (out or "").strip()
        return None if out in ("", "null") else out

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
