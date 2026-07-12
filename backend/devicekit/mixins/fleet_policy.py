"""FleetPolicyMixin — desired-state fleet policies (plan 23).

Owns the ``FleetPolicy`` lifecycle: CRUD over validated ``devicekit.yaml`` documents
(part 2), the desired-vs-live plan (part 3), apply-as-a-job (part 4), periodic drift
detection + reconcile (part 5), and scaffolding YAML from a live device (part 6).

Pure logic (spec/planner/scaffold) lives in ``devicekit/policy/``; this mixin supplies the
live-state seams: merged device list (FQL mixin), plan-18 app-driver provisioning, plan-22
schedules, ADB settings, the extension registry, and the plan-20 vault for ``fromSecret``.
"""
import logging
import os
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

POLICY_APPLY_KIND = "policy.apply"
POLICY_APPLY_DEVICE_KIND = "policy.apply.device"
POLICY_DRIFT_KIND = "policy.drift.check"
# Per-device apply budget inside the fan-out (mirrors plan 22's fan-out default).
POLICY_DEVICE_TIMEOUT_SECONDS = 600
POLICY_FANOUT_CONCURRENCY = 3
POLICY_DRIFT_INTERVAL_SECONDS = int(os.environ.get(
    "DEVICEKIT_POLICY_DRIFT_INTERVAL", "300"))

logger = logging.getLogger(__name__)


class FleetPolicyMixin:
    """Desired-state policies: declare what a device/group should look like; DeviceKit
    plans the diff, applies it as a job, and watches for drift."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_fleet_policy(self):
        """Register the apply job kinds + notification events. Called from ``Client.__init__``
        after the job system is up; idempotent."""
        if hasattr(self, "register_job_kind"):
            self.register_job_kind(POLICY_APPLY_KIND, self._job_apply_policy)
            self.register_job_kind(POLICY_APPLY_DEVICE_KIND, self._job_apply_policy_device)
            self.register_job_kind(POLICY_DRIFT_KIND, self._job_check_policy_drift)
        if hasattr(self, "ensure_scheduled_job"):
            self.ensure_scheduled_job(
                POLICY_DRIFT_KIND, POLICY_DRIFT_KIND,
                interval_seconds=POLICY_DRIFT_INTERVAL_SECONDS,
                startup_delay_seconds=60, owner_type="system", owner_id="core")
        if hasattr(self, "register_notification_event"):
            try:
                self.register_notification_event(
                    "policy.apply.succeeded", "Fleet policy applied",
                    severity="info", category="fleet")
                self.register_notification_event(
                    "policy.apply.failed", "Fleet policy apply failed",
                    severity="error", category="fleet")
                self.register_notification_event(
                    "policy.drift.detected", "Fleet policy drift detected",
                    severity="warning", category="fleet")
                self.register_notification_event(
                    "policy.drift.resolved", "Fleet policy drift resolved",
                    severity="info", category="fleet")
            except Exception as e:
                logger.warning(f"Policy notification events not registered: {e}")

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

    def _find_vault_id(self, vault_ref):
        for v in self.list_vaults():
            if vault_ref in (v.get("id"), v.get("slug")):
                return v["id"]
        return None

    def _resolve_secret_ref(self, ref):
        """``fromSecret: {vault, key}`` — vault accepted by id or slug. Raises ValueError
        when either half is missing."""
        vault_id = self._find_vault_id(ref["vault"])
        if not vault_id:
            raise ValueError(f"vault not found: {ref['vault']}")
        return self.reveal_secret(vault_id, ref["key"])["value"]

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
    # Apply (part 4): blockers refuse, empty converges, else a snapshotted job
    # ------------------------------------------------------------------
    def apply_fleet_policy(self, policy_id, triggered_by="manual"):
        """Gate + enqueue. Returns one of: ``{applied, short_circuit}`` (unchanged hash),
        ``{refused, plan}`` (blockers — the honesty rule, no --force), ``{applied, empty}``
        (already converged), or ``{job, plan}`` (parent job enqueued)."""
        policy = self.get_fleet_policy(policy_id)
        if not policy:
            raise ValueError("policy not found")
        if policy["status"] == STATUS_APPLIED and \
                policy["applied_hash"] == policy["policy_hash"]:
            return {"applied": True, "short_circuit": True, "policy": policy}
        plan = self.plan_fleet_policy(policy_id)
        if plan["blockers"]:
            return {"refused": True, "plan": plan}
        if not plan["steps"]:
            out = self._set_policy_status(policy_id, STATUS_APPLIED, detail={
                "summary": "already converged", "triggered_by": triggered_by})
            return {"applied": True, "empty": True, "policy": out}
        # The plan snapshot rides in the payload so a mid-flight edit can't change the run;
        # the handler re-checks the hash before touching anything.
        job = self.enqueue_job(
            POLICY_APPLY_KIND,
            payload={"policy_id": policy_id, "policy_hash": plan["policy_hash"],
                     "plan": plan, "triggered_by": triggered_by},
            max_attempts=1, owner_type="fleet_policy", owner_id=policy_id)
        return {"applied": False, "job": job, "plan": plan}

    def _job_apply_policy(self, job):
        """Parent apply job: global extension steps inline, then per-device fan-out as
        concurrency-capped child jobs (plan 22's pattern)."""
        payload = job.get("payload") or {}
        policy_id = payload.get("policy_id")
        plan = payload.get("plan") or {}
        policy = self.get_fleet_policy(policy_id)
        if not policy:
            return {"skipped": "policy deleted"}
        if policy["policy_hash"] != payload.get("policy_hash"):
            return {"skipped": "policy edited since enqueue"}

        result = {"policy_id": policy_id, "global_steps": [], "devices": {}}
        failed_global = False
        for step in [s for s in plan.get("steps", []) if s.get("device_id") is None]:
            result["global_steps"].append(
                self._run_policy_step(step, None, policy_id, skip=failed_global))
            if result["global_steps"][-1]["status"] == "error":
                failed_global = True
        if failed_global:
            detail = {"summary": "global step failed", "global_steps": result["global_steps"],
                      "triggered_by": payload.get("triggered_by")}
            self._set_policy_status(policy_id, STATUS_ERROR, detail=detail)
            self._notify_policy("policy.apply.failed", policy, detail["summary"])
            return result

        device_steps = {}
        for step in plan.get("steps", []):
            if step.get("device_id") is not None:
                device_steps.setdefault(step["device_id"], []).append(step)
        result["devices"] = self._fan_out_policy_devices(
            policy_id, payload.get("policy_hash"), device_steps)

        failures = {did: r for did, r in result["devices"].items() if not r.get("ok")}
        if failures:
            detail = {"summary": f"{len(failures)}/{len(device_steps)} device(s) failed",
                      "devices": {did: {"ok": r.get("ok", False),
                                        "error": r.get("error")}
                                  for did, r in result["devices"].items()},
                      "triggered_by": payload.get("triggered_by")}
            self._set_policy_status(policy_id, STATUS_ERROR, detail=detail)
            self._notify_policy("policy.apply.failed", policy, detail["summary"])
        else:
            detail = {"summary": f"applied to {len(device_steps)} device(s)",
                      "triggered_by": payload.get("triggered_by")}
            self._set_policy_status(policy_id, STATUS_APPLIED, detail=detail,
                                    applied_hash=payload.get("policy_hash"))
            self._notify_policy("policy.apply.succeeded", policy, detail["summary"])
        return result

    def _fan_out_policy_devices(self, policy_id, policy_hash, device_steps):
        """Bounded fan-out: at most ``min(POLICY_FANOUT_CONCURRENCY, JOB_WORKERS - 1)``
        child jobs in flight, so the waiting parent always leaves a worker free."""
        from devicekit.jobs.service import JobService
        from devicekit.mixins.jobs import JOB_WORKERS

        concurrency = max(1, min(POLICY_FANOUT_CONCURRENCY, JOB_WORKERS - 1))
        queue = sorted(device_steps.items())
        pending, results = {}, {}
        while queue or pending:
            while queue and len(pending) < concurrency:
                did, steps = queue.pop(0)
                child = self.enqueue_job(
                    POLICY_APPLY_DEVICE_KIND,
                    payload={"policy_id": policy_id, "policy_hash": policy_hash,
                             "device_id": did, "steps": steps},
                    max_attempts=1, owner_type="fleet_policy", owner_id=policy_id)
                pending[child["id"]] = (did, time.time() + POLICY_DEVICE_TIMEOUT_SECONDS)
            time.sleep(0.2)
            for job_id, (did, deadline) in list(pending.items()):
                row = JobService.get(job_id)
                status = (row or {}).get("status")
                if status in ("succeeded", "failed", "cancelled"):
                    res = (row or {}).get("result") or {}
                    if status != "succeeded" or not res:
                        res = {"device_id": did, "ok": False,
                               "error": (row or {}).get("error_message") or status}
                    results[did] = res
                    pending.pop(job_id)
                elif time.time() > deadline:
                    try:
                        JobService.cancel(job_id)
                    except Exception:
                        pass
                    results[did] = {"device_id": did, "ok": False, "error": "timeout"}
                    pending.pop(job_id)
        return results

    def _job_apply_policy_device(self, job):
        """Child job: one device — before snapshot, ordered steps with stop-on-first-failure
        (remaining steps ``skipped``), after snapshot. Failure is data (``ok: False``), not a
        job crash, so the parent aggregates cleanly."""
        payload = job.get("payload") or {}
        policy_id = payload.get("policy_id")
        did = payload.get("device_id")
        steps = payload.get("steps") or []
        policy = self.get_fleet_policy(policy_id)
        eff = (effective_spec_for_device(policy["normalized"], did)
               if policy else None)
        before = self._policy_device_snapshot(eff, did) if eff else {}
        step_results, failed = [], False
        for step in steps:
            outcome = self._run_policy_step(step, did, policy_id, skip=failed)
            step_results.append(outcome)
            if outcome["status"] == "error":
                failed = True
        after = self._policy_device_snapshot(eff, did) if eff else {}
        return {"device_id": did, "ok": not failed, "steps": step_results,
                "before": before, "after": after,
                "error": next((s.get("error") for s in step_results
                               if s["status"] == "error"), None)}

    def _run_policy_step(self, step, device_id, policy_id, skip=False):
        """Execute one step → ``{id, kind, status: ok|error|skipped, ...}``, broadcasting
        progress on the ``policy`` SSE channel."""
        outcome = {"id": step.get("id"), "kind": step.get("kind")}
        if skip:
            outcome["status"] = "skipped"
        else:
            try:
                detail = self._exec_policy_step(step, device_id)
                outcome.update({"status": "ok", "detail": detail})
            except Exception as e:
                outcome.update({"status": "error", "error": str(e)})
        try:
            self.broadcast("policy", {"event": "apply_step", "policy_id": policy_id,
                                      "device_id": device_id, "step": outcome})
        except Exception:
            pass
        return outcome

    def _exec_policy_step(self, step, device_id):
        kind = step["kind"]
        if kind == "attach_extension":
            slug = step["extension"]
            if step["action"] == "enable":
                self.enable_extension(slug)
            else:
                self.install_extension_from_registry(slug)
            ext = self.get_extension(slug)
            if not ext or ext.get("status") != "active":
                raise RuntimeError(f"extension {slug} is not active after "
                                   f"{step['action']}")
            return {"extension": slug, "action": step["action"]}
        if kind == "provision_app":
            from devicekit_sdk import appdriver
            slug = step["extension"]
            config = self.get_extension_config_raw(slug)
            if not config.get("apk_b64"):
                raise RuntimeError(f"no APK configured on {slug} to provision "
                                   f"{step['package']}")
            record = appdriver.provision(
                slug, device_id, package=step["package"],
                apk_b64=config["apk_b64"],
                expected_sha256=config.get("apk_sha256"),
                expected_version=config.get("apk_version"),
                serial=device_id)
            version = record.get("version_name") if isinstance(record, dict) else None
            return {"package": step["package"], "version": version}
        if kind == "configure_setting":
            ns, key = step["namespace"], step["key"]
            if step.get("secret"):
                value = self._resolve_or_generate_secret(step)
            else:
                value = step["value"]
            self.run_adb_command(["shell", "settings", "put", ns, key, str(value)],
                                 device=device_id)
            actual = self._adb_get_setting(device_id, ns, key)
            if actual != str(value):
                raise RuntimeError(
                    f"settings put verification failed for {ns}.{key} (got {actual!r})")
            return {"namespace": ns, "key": key, "secret": bool(step.get("secret"))}
        if kind == "enable_automation":
            action = step["action"]
            if action == "create":
                schedule = self.create_schedule(step["automation_id"], device_id,
                                                step["interval_minutes"], enabled=True)
                return {"action": action, "schedule_id": schedule["id"]}
            updates = ({"enabled": False} if action == "disable"
                       else {"interval_minutes": step["interval_minutes"], "enabled": True})
            if not self.update_schedule(step["schedule_id"], updates):
                raise RuntimeError(f"schedule {step['schedule_id']} vanished")
            return {"action": action, "schedule_id": step["schedule_id"]}
        raise ValueError(f"unknown step kind: {kind}")

    def _resolve_or_generate_secret(self, step):
        """Re-resolve the ``fromSecret`` ref at execution time (never trust a value smuggled
        through a job payload). ``generate: true`` mints + stores the value on first use."""
        import secrets as pysecrets
        ref = step["from_secret"]
        try:
            return self._resolve_secret_ref(ref)
        except ValueError:
            if not step.get("generate"):
                raise
            vault_id = self._find_vault_id(ref["vault"])
            if not vault_id:
                raise RuntimeError(f"cannot generate {ref['key']}: vault "
                                   f"{ref['vault']} does not exist")
            value = pysecrets.token_urlsafe(24)
            self.set_secret(vault_id, ref["key"], value,
                            description="generated by fleet policy apply")
            return value

    def _policy_device_snapshot(self, eff, device_id):
        """Before/after evidence for the apply record: only what the policy governs."""
        snap = {"apps": {}, "settings": {}, "automations": {}}
        try:
            for app in eff.get("apps") or []:
                snap["apps"][app["package"]] = self._adb_installed_version(
                    device_id, app["package"])
            for ns, kv in (eff.get("settings") or {}).items():
                for key in kv:
                    snap["settings"][f"{ns}.{key}"] = self._adb_get_setting(
                        device_id, ns, key)
            for auto in eff.get("automations") or []:
                state = self._automation_live_state(auto["automation"], device_id)
                snap["automations"][auto["automation"]] = state.get("schedule")
        except Exception as e:
            snap["error"] = str(e)
        return snap

    def _notify_policy(self, event_key, policy, summary):
        if not hasattr(self, "notify_event"):
            return
        try:
            self.notify_event(event_key,
                              data={"policy_id": policy["id"], "name": policy["name"],
                                    "summary": summary},
                              subject_type="fleet_policy", subject_id=policy["id"])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Drift detection + reconcile (part 5)
    # ------------------------------------------------------------------
    def check_fleet_policy_drift(self, policy_id, auto_apply=True):
        """Re-plan an applied policy against live state. Edge-triggered: only the
        applied→drifted transition notifies; a policy that converges externally flips
        back and notifies resolution. ``autoApply`` policies reconcile themselves on the
        drift edge — never when blockers stand (the honesty rule holds unattended too)."""
        policy = self.get_fleet_policy(policy_id)
        if not policy:
            raise ValueError("policy not found")
        if policy["status"] not in (STATUS_APPLIED, STATUS_DRIFTED):
            return {"policy_id": policy_id, "checked": False, "status": policy["status"],
                    "reason": "only applied policies are drift-checked"}
        plan = self.plan_fleet_policy(policy_id)
        was = policy["status"]
        out = {"policy_id": policy_id, "checked": True, "drifted": not plan["empty"],
               "edge": False, "auto_applied": False}
        if plan["empty"]:
            if was == STATUS_DRIFTED:
                self._set_policy_status(policy_id, STATUS_APPLIED,
                                        detail={"summary": "drift resolved externally"},
                                        applied_hash=policy["applied_hash"])
                self._notify_policy("policy.drift.resolved", policy,
                                    "live state converged back to the policy")
                out["edge"] = True
            else:
                self._touch_policy_checked(policy_id)
            out["status"] = STATUS_APPLIED
            return out
        summary = {
            "summary": f"{len(plan['steps'])} step(s) diverged"
                       + (f", {len(plan['blockers'])} blocker(s)" if plan["blockers"] else ""),
            "steps": len(plan["steps"]),
            "blockers": plan["blockers"],
            "detected_at": time.time(),
        }
        if was == STATUS_APPLIED:
            self._set_policy_status(policy_id, STATUS_DRIFTED, detail=summary)
            self._notify_policy("policy.drift.detected", policy, summary["summary"])
            out["edge"] = True
            if auto_apply and policy["auto_apply"] and not plan["blockers"]:
                result = self.apply_fleet_policy(policy_id, triggered_by="auto_apply")
                out["auto_applied"] = bool(result.get("job") or result.get("applied"))
        else:
            self._touch_policy_checked(policy_id, detail=summary)
        out["status"] = STATUS_DRIFTED
        return out

    def _job_check_policy_drift(self, job):
        """Scheduled sweep over every applied/drifted policy (all workspaces)."""
        out = {"checked": 0, "drifted": 0, "resolved": 0, "auto_applied": 0}
        for policy in self.list_fleet_policies():
            if policy["status"] not in (STATUS_APPLIED, STATUS_DRIFTED):
                continue
            try:
                result = self.check_fleet_policy_drift(policy["id"])
            except Exception as e:
                logger.warning(f"Drift check failed for policy {policy['id']}: {e}")
                continue
            out["checked"] += 1
            if result.get("drifted"):
                out["drifted"] += 1
            elif result.get("edge"):
                out["resolved"] += 1
            if result.get("auto_applied"):
                out["auto_applied"] += 1
        return out

    def _touch_policy_checked(self, policy_id, detail=None):
        with session_scope() as s:
            p = s.get(FleetPolicy, policy_id)
            if not p:
                return
            p.last_checked_at = time.time()
            if detail is not None:
                p.status_detail = detail

    # ------------------------------------------------------------------
    # Scaffold (part 6): YAML from live state
    # ------------------------------------------------------------------
    def scaffold_fleet_policy(self, device_id, name=None):
        """Capture a live device as a starting-point ``devicekit.yaml``: driver-backed apps
        at their installed versions, this device's schedules, a curated settings whitelist,
        and the active extension set. Sensitive keys come back as ``fromSecret`` refs."""
        from devicekit.policy.scaffold import SCAFFOLD_SETTINGS, render_scaffold

        devices = self.all_devices_for_query()
        index = {d.get("device_id") or d.get("serial"): d for d in devices if d}
        device = index.get(device_id)
        if not device:
            raise ValueError(f"device not found: {device_id}")
        adb_reachable = device.get("source") != "agent" and bool(device.get("online"))
        issues = []
        facts = {"apps": [], "automations": [], "settings": {}, "extensions": []}
        for ext in (self.list_extensions() if hasattr(self, "list_extensions") else []):
            if ext.get("status") != "active":
                continue
            facts["extensions"].append(ext["slug"])
            package = ((ext.get("manifest") or {}).get("device_requirements")
                       or {}).get("package")
            if package and adb_reachable:
                version = self._adb_installed_version(device_id, package)
                if version:
                    facts["apps"].append({"package": package, "version": version,
                                          "extension": ext["slug"]})
        if adb_reachable:
            for ns, keys in SCAFFOLD_SETTINGS.items():
                for key in keys:
                    value = self._adb_get_setting(device_id, ns, key)
                    if value is not None:
                        facts["settings"].setdefault(ns, {})[key] = value
        else:
            issues.append("device is not ADB-reachable — installed apps and settings "
                          "were not captured")
        for schedule in (self.list_schedules()
                         if hasattr(self, "list_schedules") else []):
            if schedule.get("device_id") != device_id:
                continue
            facts["automations"].append({
                "automation": schedule.get("automation_name")
                              or schedule.get("automation_id"),
                "enabled": bool(schedule.get("enabled")),
                "schedule": {"intervalMinutes":
                             int(schedule.get("interval_minutes") or 60)},
            })
        out = render_scaffold(device_id, facts, name=name)
        out["issues"] = issues
        return out

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
