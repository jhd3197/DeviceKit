"""OnboardingMixin — device enrollment as a state machine on the job bus (plan 25 part 4).

Replaces ad-hoc pairing with a formal, observable, restart-safe lifecycle:
``pending → validating → provisioning → ready | failed``. Each transition is its own
``onboarding.advance`` job — so a crash mid-onboarding resumes from the last persisted state,
and the ordered ``steps`` log shows exactly where a device is (or why it failed).

The machine wires plan 25 to the rest of the platform: **validating** confirms the device is
reachable and snapshots its capabilities; **provisioning** applies any fleet policy (plan 23)
whose target includes the device, so a newly-``ready`` device already matches its group's
desired state. Every hook degrades gracefully if the peer mixin isn't present.
"""
import time
import uuid
import logging

from devicekit.db import session_scope
from devicekit.models import OnboardingSession
from devicekit.models.onboarding import (
    STATE_PENDING, STATE_VALIDATING, STATE_PROVISIONING, STATE_READY, STATE_FAILED,
    TERMINAL_STATES)

logger = logging.getLogger(__name__)

ONBOARDING_ADVANCE_KIND = "onboarding.advance"

# What state each advance transitions INTO from the current one (does that state's work).
_NEXT_STATE = {
    STATE_PENDING: STATE_VALIDATING,
    STATE_VALIDATING: STATE_PROVISIONING,
    STATE_PROVISIONING: STATE_READY,
}


class OnboardingMixin:
    """Formal device onboarding advanced one transition per job."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_onboarding(self):
        if hasattr(self, "register_job_kind"):
            self.register_job_kind(ONBOARDING_ADVANCE_KIND, self._job_advance_onboarding)
        if hasattr(self, "register_notification_event"):
            for key, title, sev in (
                ("onboarding.ready", "Device onboarded", "info"),
                ("onboarding.failed", "Device onboarding failed", "error"),
            ):
                try:
                    self.register_notification_event(key, title, severity=sev, category="fleet")
                except Exception as e:
                    logger.warning(f"Onboarding event {key} not registered: {e}")

    # ------------------------------------------------------------------
    # Start / restart
    # ------------------------------------------------------------------
    def start_onboarding(self, device_id, serial=None, context=None, workspace_id=None):
        """Create (or restart) an onboarding session in ``pending`` and enqueue the first
        advance. If a non-terminal session already exists for the device it is returned
        as-is (idempotent — a re-register won't spawn a parallel onboarding)."""
        existing = self.get_onboarding_session_for_device(device_id)
        if existing and existing["state"] not in TERMINAL_STATES:
            return existing
        now = time.time()
        session_id = str(uuid.uuid4())
        with session_scope() as s:
            row = OnboardingSession(
                id=session_id, device_id=device_id, serial=serial,
                state=STATE_PENDING, steps=[], context=context or {},
                started_at=now, updated_at=now, workspace_id=workspace_id)
            s.add(row)
            s.flush()
            out = row.to_dict()
        self._broadcast_onboarding("started", out)
        self._enqueue_advance(session_id)
        return out

    def restart_onboarding(self, session_id):
        """Reset a session to ``pending`` (clearing the log) and re-enqueue advancement."""
        with session_scope() as s:
            row = s.get(OnboardingSession, session_id)
            if not row:
                return None
            row.state = STATE_PENDING
            row.steps = []
            row.error = None
            row.completed_at = None
            row.updated_at = time.time()
            out = row.to_dict()
        self._broadcast_onboarding("restarted", out)
        self._enqueue_advance(session_id)
        return out

    def _enqueue_advance(self, session_id):
        if hasattr(self, "enqueue_job"):
            self.enqueue_job(ONBOARDING_ADVANCE_KIND, payload={"session_id": session_id},
                             max_attempts=1, owner_type="onboarding", owner_id=session_id)

    # ------------------------------------------------------------------
    # The state machine (one transition per job)
    # ------------------------------------------------------------------
    def _job_advance_onboarding(self, job):
        return self.advance_onboarding((job.get("payload") or {}).get("session_id"))

    def advance_onboarding(self, session_id):
        """Perform the work for the current state's next transition, append a step, and either
        enqueue the following advance or finish. A step that fails moves the session to
        ``failed`` and stops."""
        session = self.get_onboarding_session(session_id)
        if not session:
            return {"error": "session not found"}
        state = session["state"]
        if state in TERMINAL_STATES:
            return {"session_id": session_id, "state": state, "done": True}

        target = _NEXT_STATE.get(state)
        if target is None:
            return {"session_id": session_id, "state": state, "noop": True}

        # Run the entering-state's work.
        try:
            if target == STATE_VALIDATING:
                ok, detail = self._onboarding_validate(session)
                step = "validate"
            elif target == STATE_PROVISIONING:
                ok, detail = self._onboarding_provision(session)
                step = "provision"
            else:  # STATE_READY
                ok, detail = True, {"summary": "onboarding complete"}
                step = "finalize"
        except Exception as e:
            ok, detail, step = False, {"error": str(e)}, _NEXT_STATE.get(state, "advance")

        if not ok:
            self._record_step(session_id, step, "error", detail)
            self._set_onboarding_state(session_id, STATE_FAILED,
                                       error=(detail or {}).get("error") or f"{step} failed")
            self._notify_onboarding("onboarding.failed", session, step)
            return {"session_id": session_id, "state": STATE_FAILED, "failed_step": step}

        self._record_step(session_id, step, "ok", detail)
        self._set_onboarding_state(session_id, target)
        if target == STATE_READY:
            self._notify_onboarding("onboarding.ready", session, step)
            return {"session_id": session_id, "state": STATE_READY, "done": True}
        # More to do — advance again on the bus so each transition is its own observable job.
        self._enqueue_advance(session_id)
        return {"session_id": session_id, "state": target}

    # ------------------------------------------------------------------
    # State work (each hook degrades gracefully)
    # ------------------------------------------------------------------
    def _onboarding_validate(self, session):
        """Confirm the device is reachable and snapshot its capabilities. Failure here means
        the device never checked in, so onboarding can't proceed."""
        device_id = session["device_id"]
        state = (self.find_agent_device(device_id)
                 if hasattr(self, "find_agent_device") else None)
        if state is None and hasattr(self, "all_devices_for_query"):
            # Fall back to the merged ADB+agent fleet list.
            for d in (self.all_devices_for_query() or []):
                if d and (d.get("device_id") == device_id or d.get("serial") == device_id):
                    state = d
                    break
        if state is None:
            return False, {"error": f"device {device_id} not reachable — no registration"}
        caps = (state.get("capabilities") if isinstance(state, dict) else None) or {}
        return True, {"summary": "device reachable", "capabilities": list(caps.keys()),
                      "online": bool(state.get("online"))}

    def _onboarding_provision(self, session):
        """Apply any fleet policy (plan 23) whose target includes this device, so a ready
        device already matches its group's desired state. No matching policy is success, not
        failure — a device can be onboarded before any policy exists."""
        device_id = session["device_id"]
        applied = []
        if not hasattr(self, "list_fleet_policies") or not hasattr(self, "apply_fleet_policy"):
            return True, {"summary": "no fleet-policy engine; nothing to provision"}
        try:
            policies = self.list_fleet_policies()
        except Exception as e:
            return True, {"summary": f"policy list unavailable: {e}"}
        for policy in policies:
            try:
                if not self._policy_targets_device(policy, device_id):
                    continue
                result = self.apply_fleet_policy(policy["id"], triggered_by="onboarding")
                applied.append({"policy_id": policy["id"], "name": policy.get("name"),
                                "outcome": "job" if result.get("job") else
                                           ("applied" if result.get("applied") else
                                            "refused" if result.get("refused") else "unknown")})
            except Exception as e:
                logger.warning(f"Onboarding provision policy {policy.get('id')} failed: {e}")
        return True, {"summary": f"{len(applied)} policy/policies applied", "applied": applied}

    def _policy_targets_device(self, policy, device_id):
        """True if a fleet policy's target resolves to include ``device_id``."""
        if not hasattr(self, "_resolve_policy_devices"):
            return False
        try:
            ids, _ = self._resolve_policy_devices(policy["target_kind"], policy["target_value"])
            return device_id in (ids or [])
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Persistence + reads
    # ------------------------------------------------------------------
    def _record_step(self, session_id, step, status, detail):
        with session_scope() as s:
            row = s.get(OnboardingSession, session_id)
            if not row:
                return
            log = list(row.steps or [])
            log.append({"step": step, "status": status, "detail": detail, "at": time.time()})
            row.steps = log
            row.updated_at = time.time()

    def _set_onboarding_state(self, session_id, state, error=None):
        with session_scope() as s:
            row = s.get(OnboardingSession, session_id)
            if not row:
                return None
            row.state = state
            row.error = error
            row.updated_at = time.time()
            if state in TERMINAL_STATES:
                row.completed_at = time.time()
            out = row.to_dict()
        self._broadcast_onboarding("state", out)
        return out

    def get_onboarding_session(self, session_id):
        with session_scope() as s:
            row = s.get(OnboardingSession, session_id)
            return row.to_dict() if row else None

    def get_onboarding_session_for_device(self, device_id):
        """The most recent session for a device (any state)."""
        with session_scope() as s:
            row = (s.query(OnboardingSession)
                   .filter(OnboardingSession.device_id == device_id)
                   .order_by(OnboardingSession.started_at.desc()).first())
            return row.to_dict() if row else None

    def list_onboarding_sessions(self, state=None, limit=100):
        with session_scope() as s:
            q = s.query(OnboardingSession)
            if state:
                q = q.filter(OnboardingSession.state == state)
            rows = q.order_by(OnboardingSession.started_at.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _broadcast_onboarding(self, event, session_dict):
        try:
            self.broadcast("onboarding", {"event": event, "session": session_dict})
        except Exception:
            pass

    def _notify_onboarding(self, event_key, session, step):
        if not hasattr(self, "notify_event"):
            return
        try:
            self.notify_event(
                event_key,
                data={"device_id": session["device_id"], "session_id": session["id"],
                      "step": step},
                subject_type="device", subject_id=session["device_id"])
        except Exception:
            pass
