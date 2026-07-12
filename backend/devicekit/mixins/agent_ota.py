"""AgentOtaMixin — OTA agent updates (plan 25 part 3, greenfield).

Roll a new agent APK to the whole fleet without touching a phone:

* the backend hosts **signed** releases (Ed25519 over a manifest that pins the APK sha256);
* agents **pull** an update on a **rollout policy** (canary → staged → full) — pull survives
  NAT and flaky links, which push does not (the decision logged in the plan);
* the rollout advances on the **job bus** (a scheduled ``ota.rollout.advance`` job), so it is
  restart-safe and observable, and **auto-rolls-back** if the failure rate crosses a
  threshold;
* a device that boot-loops on a bad build hits **crash-loop backoff** (per-device attempt
  cap) and stops being offered the update.

The signing primitive lives in ``devicekit.ota.signing``; the pure cohort/advance policy in
``devicekit.ota.rollout``. This mixin is the stateful seam: releases on disk + rows, rollout
lifecycle, and the agent-pull endpoints' backing methods.
"""
import io
import os
import time
import uuid
import hashlib
import logging
import zipfile

from devicekit.db import session_scope
from devicekit.models import AgentRelease, AgentRollout, AgentUpdateState
from devicekit.models.agent_release import STATUS_PUBLISHED, STATUS_YANKED
from devicekit.models.agent_rollout import (
    STATUS_ACTIVE, STATUS_COMPLETED, STATUS_ROLLED_BACK, STATUS_PAUSED)
from devicekit.models.agent_update_state import (
    STATUS_OFFERED, STATUS_INSTALLED, STATUS_FAILED)
from devicekit.ota import signing
from devicekit.ota.rollout import (
    normalize_config, in_cohort, evaluate_rollout)

logger = logging.getLogger(__name__)

OTA_ADVANCE_KIND = "ota.rollout.advance"


class AgentOtaMixin:
    """Signed releases + rollout policy + agent-pull update endpoints."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_agent_ota(self):
        """Register the advance job + schedule + notification events. After the job system."""
        self._ota_key = None
        if hasattr(self, "register_job_kind"):
            self.register_job_kind(OTA_ADVANCE_KIND, self._job_advance_rollouts)
        if hasattr(self, "ensure_scheduled_job"):
            try:
                from config import OTA_ROLLOUT_ADVANCE_INTERVAL
            except Exception:
                OTA_ROLLOUT_ADVANCE_INTERVAL = 60
            self.ensure_scheduled_job(
                OTA_ADVANCE_KIND, OTA_ADVANCE_KIND,
                interval_seconds=OTA_ROLLOUT_ADVANCE_INTERVAL,
                startup_delay_seconds=45, owner_type="system", owner_id="core")
        if hasattr(self, "register_notification_event"):
            for key, title, sev in (
                ("ota.release.published", "Agent release published", "info"),
                ("ota.rollout.advanced", "OTA rollout advanced a stage", "info"),
                ("ota.rollout.completed", "OTA rollout completed", "info"),
                ("ota.rollout.rolledback", "OTA rollout rolled back", "warning"),
            ):
                try:
                    self.register_notification_event(key, title, severity=sev, category="fleet")
                except Exception as e:
                    logger.warning(f"OTA notification event {key} not registered: {e}")

    # ------------------------------------------------------------------
    # Signing key + storage
    # ------------------------------------------------------------------
    def _ota_private_key(self):
        if getattr(self, "_ota_key", None) is None:
            from config import OTA_SIGNING_KEY_PATH
            self._ota_key = signing.load_or_create_private_key(OTA_SIGNING_KEY_PATH)
        return self._ota_key

    def ota_public_key(self):
        """Hex Ed25519 public key the agent pins to verify release manifests."""
        return signing.public_key_hex(self._ota_private_key())

    def _ota_apk_dir(self):
        d = os.path.join(getattr(self, "output_dir", "output"), "ota", "apks")
        os.makedirs(d, exist_ok=True)
        return d

    def _ota_apk_path(self, release_id):
        return os.path.join(self._ota_apk_dir(), f"{release_id}.apk")

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------
    def create_agent_release(self, apk_bytes, version_name, version_code,
                             notes=None, filename=None, created_by=None):
        """Register a signed release from raw APK bytes.

        Computes the sha256, signs the manifest with the OTA key, writes the bytes to disk,
        and persists the row. Raises ``ValueError`` on bad inputs (empty bytes, non-int
        version code, or bytes that aren't a ZIP/APK)."""
        if not apk_bytes:
            raise ValueError("empty APK")
        try:
            version_code = int(version_code)
        except (TypeError, ValueError):
            raise ValueError("version_code must be an integer")
        if not version_name:
            raise ValueError("version_name required")
        # A real APK is a ZIP; reject obvious garbage early so a rollout can't ship a brick.
        if not zipfile.is_zipfile(io.BytesIO(apk_bytes)):
            raise ValueError("payload is not a valid APK (zip) file")

        release_id = str(uuid.uuid4())
        sha = hashlib.sha256(apk_bytes).hexdigest()
        size = len(apk_bytes)
        manifest = {
            "release_id": release_id,
            "version_name": str(version_name),
            "version_code": version_code,
            "sha256": sha,
            "size_bytes": size,
        }
        key = self._ota_private_key()
        signature = signing.sign_manifest(key, manifest)
        public_key = signing.public_key_hex(key)

        # Write bytes before the row commits so a published row always has its file.
        path = self._ota_apk_path(release_id)
        with open(path, "wb") as f:
            f.write(apk_bytes)

        with session_scope() as s:
            row = AgentRelease(
                id=release_id, version_name=str(version_name), version_code=version_code,
                sha256=sha, size_bytes=size, signature=signature, public_key=public_key,
                filename=filename, notes=notes, status=STATUS_PUBLISHED,
                created_at=time.time(), created_by=created_by)
            s.add(row)
            s.flush()
            out = row.to_dict()
        self._broadcast_ota("release_published", {"release": out})
        self._notify_ota("ota.release.published", {"version_name": out["version_name"],
                                                   "version_code": out["version_code"]})
        return out

    def list_agent_releases(self):
        with session_scope() as s:
            return [r.to_dict() for r in
                    s.query(AgentRelease).order_by(AgentRelease.created_at.desc()).all()]

    def get_agent_release(self, release_id):
        with session_scope() as s:
            r = s.get(AgentRelease, release_id)
            return r.to_dict() if r else None

    def yank_agent_release(self, release_id):
        """Mark a release yanked so no new rollout can offer it (existing rollouts of it are
        left to an operator to roll back explicitly)."""
        with session_scope() as s:
            r = s.get(AgentRelease, release_id)
            if not r:
                return None
            r.status = STATUS_YANKED
            return r.to_dict()

    def get_release_apk(self, release_id):
        """Return ``(bytes, filename)`` for a release, or ``(None, None)`` if missing."""
        rel = self.get_agent_release(release_id)
        if not rel:
            return None, None
        path = self._ota_apk_path(release_id)
        if not os.path.exists(path):
            return None, None
        with open(path, "rb") as f:
            return f.read(), (rel.get("filename") or f"agent-{rel['version_name']}.apk")

    def signed_release_payload(self, release, download_path):
        """The agent-pull response for a release: the *signed* manifest plus the unsigned
        download path (integrity rides the signed sha256, not the URL)."""
        return {
            "update": True,
            "manifest": {
                "release_id": release["id"],
                "version_name": release["version_name"],
                "version_code": release["version_code"],
                "sha256": release["sha256"],
                "size_bytes": release["size_bytes"],
            },
            "signature": release["signature"],
            "public_key": release["public_key"],
            "download_path": download_path,
        }

    # ------------------------------------------------------------------
    # Rollouts
    # ------------------------------------------------------------------
    def create_agent_rollout(self, release_id, target_kind="all", target_value=None,
                             config=None, created_by=None, workspace_id=None,
                             rollback_of=None):
        """Start a rollout of a published release. Begins at the canary stage immediately so
        in-cohort devices are offered the update on their next check."""
        rel = self.get_agent_release(release_id)
        if not rel:
            raise ValueError("release not found")
        if rel["status"] != STATUS_PUBLISHED:
            raise ValueError(f"release is {rel['status']}, cannot roll out")
        now = time.time()
        rollout_id = str(uuid.uuid4())
        with session_scope() as s:
            row = AgentRollout(
                id=rollout_id, release_id=release_id, target_kind=target_kind,
                target_value=target_value, stage="canary", status=STATUS_ACTIVE,
                config=normalize_config(config), stage_entered_at=now,
                rollback_of=rollback_of, created_at=now, created_by=created_by,
                workspace_id=workspace_id)
            s.add(row)
            s.flush()
            out = row.to_dict()
        self._broadcast_ota("rollout_created", {"rollout": out})
        return out

    def list_agent_rollouts(self, status=None):
        with session_scope() as s:
            q = s.query(AgentRollout)
            if status:
                q = q.filter(AgentRollout.status == status)
            rows = q.order_by(AgentRollout.created_at.desc()).all()
            out = [r.to_dict() for r in rows]
        for r in out:
            r["progress"] = self.rollout_progress(r["id"])
        return out

    def get_agent_rollout(self, rollout_id):
        with session_scope() as s:
            r = s.get(AgentRollout, rollout_id)
            out = r.to_dict() if r else None
        if out:
            out["progress"] = self.rollout_progress(rollout_id)
        return out

    def rollout_progress(self, rollout_id):
        """Aggregate per-device update state for a rollout, by status."""
        counts = {}
        with session_scope() as s:
            for st in s.query(AgentUpdateState).filter(
                    AgentUpdateState.rollout_id == rollout_id).all():
                counts[st.status] = counts.get(st.status, 0) + 1
        return {
            "offered": counts.get(STATUS_OFFERED, 0),
            "installed": counts.get(STATUS_INSTALLED, 0),
            "failed": counts.get(STATUS_FAILED, 0),
            "in_progress": sum(v for k, v in counts.items()
                               if k not in (STATUS_INSTALLED, STATUS_FAILED, STATUS_OFFERED)),
            "total": sum(counts.values()),
        }

    def set_rollout_paused(self, rollout_id, paused):
        with session_scope() as s:
            r = s.get(AgentRollout, rollout_id)
            if not r or r.status in (STATUS_COMPLETED, STATUS_ROLLED_BACK):
                return None
            r.status = STATUS_PAUSED if paused else STATUS_ACTIVE
            r.updated_at = time.time()
            out = r.to_dict()
        self._broadcast_ota("rollout_status", {"rollout": out})
        return out

    def rollback_rollout(self, rollout_id, reason=None, auto=False):
        """Stop a rollout and, if a prior published version exists, open a rollback rollout
        to it. Devices already updated can't be un-flashed remotely, but new offers stop and
        the fleet is steered back to the last-good build."""
        rel_prev = None
        with session_scope() as s:
            r = s.get(AgentRollout, rollout_id)
            if not r:
                return None
            if r.status not in (STATUS_ACTIVE, STATUS_PAUSED):
                return {"rolled_back": r.to_dict(), "rollback": None,
                        "note": f"rollout already {r.status}"}
            r.status = STATUS_ROLLED_BACK
            r.status_detail = {"reason": reason or "manual rollback", "auto": auto,
                               "at": time.time()}
            r.updated_at = time.time()
            rolled = r.to_dict()
            current = s.get(AgentRelease, r.release_id)
            # Prior published release = highest version_code below the current one.
            if current:
                prev = (s.query(AgentRelease)
                        .filter(AgentRelease.status == STATUS_PUBLISHED,
                                AgentRelease.version_code < current.version_code)
                        .order_by(AgentRelease.version_code.desc()).first())
                rel_prev = prev.id if prev else None
                target_kind = r.target_kind
                target_value = r.target_value
                cfg = dict(r.config or {})
        self._broadcast_ota("rollout_status", {"rollout": rolled})
        self._notify_ota("ota.rollout.rolledback",
                         {"rollout_id": rollout_id, "reason": reason or "manual rollback"})
        rollback = None
        if rel_prev:
            # Fast dwell on a rollback — we already know the target is good.
            cfg["dwell_seconds"] = min(int(cfg.get("dwell_seconds", 3600)), 300)
            rollback = self.create_agent_rollout(
                rel_prev, target_kind=target_kind, target_value=target_value,
                config=cfg, rollback_of=rollout_id)
        return {"rolled_back": rolled, "rollback": rollback}

    # ------------------------------------------------------------------
    # Advance (scheduled job): canary → staged → full → completed | rolled_back
    # ------------------------------------------------------------------
    def _job_advance_rollouts(self, job):
        return self.advance_rollouts()

    def advance_rollouts(self):
        """Evaluate every active rollout and apply one transition each. Restart-safe: state
        is all in rows, so a crash mid-sweep just re-evaluates next tick."""
        now = time.time()
        summary = {"advanced": 0, "completed": 0, "rolled_back": 0, "held": 0}
        for rollout in self.list_agent_rollouts(status=STATUS_ACTIVE):
            stats = rollout["progress"]
            decision = evaluate_rollout(
                rollout["stage"], rollout["stage_entered_at"], now, stats, rollout["config"])
            action = decision["action"]
            if action == "hold":
                summary["held"] += 1
            elif action == "advance":
                self._enter_stage(rollout["id"], decision["next_stage"])
                summary["advanced"] += 1
                self._notify_ota("ota.rollout.advanced",
                                 {"rollout_id": rollout["id"], "stage": decision["next_stage"]})
            elif action == "complete":
                self._complete_rollout(rollout["id"])
                summary["completed"] += 1
                self._notify_ota("ota.rollout.completed", {"rollout_id": rollout["id"]})
            elif action == "rollback":
                self.rollback_rollout(rollout["id"], reason=decision.get("reason"), auto=True)
                summary["rolled_back"] += 1
        return summary

    def _enter_stage(self, rollout_id, stage):
        with session_scope() as s:
            r = s.get(AgentRollout, rollout_id)
            if not r or r.status != STATUS_ACTIVE:
                return
            r.stage = stage
            r.stage_entered_at = time.time()
            r.updated_at = time.time()
            out = r.to_dict()
        self._broadcast_ota("rollout_stage", {"rollout": out})

    def _complete_rollout(self, rollout_id):
        with session_scope() as s:
            r = s.get(AgentRollout, rollout_id)
            if not r or r.status != STATUS_ACTIVE:
                return
            r.status = STATUS_COMPLETED
            r.updated_at = time.time()
            out = r.to_dict()
        self._broadcast_ota("rollout_status", {"rollout": out})

    # ------------------------------------------------------------------
    # Agent-pull: "is there an update for me?" + progress reporting
    # ------------------------------------------------------------------
    def check_device_update(self, device_id, download_path_builder=None):
        """Return a signed release payload if an active rollout offers ``device_id`` an update,
        else ``{"update": False}``.

        Gates, in order: rollout targets the device → device is in the stage cohort → device
        isn't already on the release → device hasn't crash-looped on it. The chosen rollout is
        the one offering the newest version the device isn't already running (rollbacks may
        offer an *older* version, which is intended).
        """
        did = self._resolve_agent_device_id(device_id) if hasattr(
            self, "_resolve_agent_device_id") else device_id
        current_code = self._device_version_code(did)
        try:
            from config import OTA_MAX_UPDATE_ATTEMPTS
        except Exception:
            OTA_MAX_UPDATE_ATTEMPTS = 3

        best = None  # (release, rollout)
        for rollout in self.list_agent_rollouts(status=STATUS_ACTIVE):
            if not self._rollout_targets_device(rollout, did):
                continue
            if not in_cohort(did, rollout["stage"], rollout["config"]):
                continue
            rel = self.get_agent_release(rollout["release_id"])
            if not rel or rel["status"] != STATUS_PUBLISHED:
                continue
            is_rollback = rollout.get("rollback_of") is not None
            if not self._should_offer(current_code, rel["version_code"], is_rollback):
                continue
            # Crash-loop backoff: skip if this device already exhausted its attempts.
            state = self._get_update_state(rollout["id"], did)
            if state and state["status"] == STATUS_FAILED and \
                    state["attempts"] >= OTA_MAX_UPDATE_ATTEMPTS:
                continue
            if state and state["status"] == STATUS_INSTALLED:
                continue
            if best is None or rel["version_code"] > best[0]["version_code"]:
                best = (rel, rollout)

        if not best:
            return {"update": False}
        rel, rollout = best
        self._ensure_update_state(rollout["id"], did, rel["id"], rel["version_code"])
        path = (download_path_builder(rel["id"]) if download_path_builder
                else f"/agent-device/ota/releases/{rel['id']}/apk")
        payload = self.signed_release_payload(rel, path)
        payload["rollout_id"] = rollout["id"]
        return payload

    def report_device_update(self, device_id, rollout_id, status, version_code=None,
                             error=None):
        """Agent reports progress for an offered release. Drives rollout stats + crash-loop
        backoff. On ``failed`` the attempt count increments; on ``installed`` the device's
        known version is bumped so it isn't re-offered."""
        did = self._resolve_agent_device_id(device_id) if hasattr(
            self, "_resolve_agent_device_id") else device_id
        now = time.time()
        with session_scope() as s:
            st = (s.query(AgentUpdateState)
                  .filter(AgentUpdateState.rollout_id == rollout_id,
                          AgentUpdateState.device_id == did).first())
            if not st:
                rel_id = None
                rollout = s.get(AgentRollout, rollout_id)
                rel_id = rollout.release_id if rollout else None
                st = AgentUpdateState(
                    id=str(uuid.uuid4()), rollout_id=rollout_id, device_id=did,
                    release_id=rel_id or "", target_version_code=version_code,
                    status=STATUS_OFFERED, attempts=0, created_at=now)
                s.add(st)
            st.status = status
            st.updated_at = now
            if version_code is not None:
                st.target_version_code = version_code
            if status == STATUS_FAILED:
                st.attempts = (st.attempts or 0) + 1
                st.last_error = (error or "install failed")[:500]
            out = st.to_dict()
        if status == STATUS_INSTALLED and version_code is not None and hasattr(
                self, "update_agent_device_fields"):
            try:
                self.update_agent_device_fields(did, agent_version_code=version_code)
            except Exception:
                pass
        self._broadcast_ota("update_status", {"device_id": did, "rollout_id": rollout_id,
                                              "status": status})
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _device_version_code(self, device_id):
        state = (self.find_agent_device(device_id)
                 if hasattr(self, "find_agent_device") else None)
        return (state or {}).get("agent_version_code")

    @staticmethod
    def _should_offer(current_code, release_code, is_rollback):
        if current_code is None:
            return True
        if is_rollback:
            return current_code != release_code  # a rollback may downgrade
        return current_code < release_code

    def _rollout_targets_device(self, rollout, device_id):
        kind = rollout.get("target_kind", "all")
        if kind == "all":
            return True
        value = rollout.get("target_value")
        if kind == "group":
            try:
                group = self.get_device_group(value) if hasattr(self, "get_device_group") else None
                return bool(group and device_id in (group.get("device_ids") or []))
            except Exception:
                return False
        if kind == "fql":
            try:
                devices = self.all_devices_for_query() if hasattr(
                    self, "all_devices_for_query") else []
                matched = self.execute_fleet_query(value, devices=devices)
                ids = {d.get("device_id") or d.get("serial") for d in matched}
                return device_id in ids
            except Exception:
                return False
        return False

    def _get_update_state(self, rollout_id, device_id):
        with session_scope() as s:
            st = (s.query(AgentUpdateState)
                  .filter(AgentUpdateState.rollout_id == rollout_id,
                          AgentUpdateState.device_id == device_id).first())
            return st.to_dict() if st else None

    def _ensure_update_state(self, rollout_id, device_id, release_id, version_code):
        with session_scope() as s:
            st = (s.query(AgentUpdateState)
                  .filter(AgentUpdateState.rollout_id == rollout_id,
                          AgentUpdateState.device_id == device_id).first())
            if st:
                return
            s.add(AgentUpdateState(
                id=str(uuid.uuid4()), rollout_id=rollout_id, device_id=device_id,
                release_id=release_id, target_version_code=version_code,
                status=STATUS_OFFERED, attempts=0, created_at=time.time()))

    def _broadcast_ota(self, event, data):
        try:
            self.broadcast("ota", {"event": event, **data})
        except Exception:
            pass

    def _notify_ota(self, event_key, data):
        if not hasattr(self, "notify_event"):
            return
        try:
            self.notify_event(event_key, data=data, subject_type="ota")
        except Exception:
            pass
