"""Confirmation gate + session modes + audit trail for the device AI agent (plan 13).

The per-device Prompture agent's tools act on real hardware. Write tools (tap, install,
``adb shell``, reboot, ...) must not run unmediated. This mixin is the human-in-the-loop
seam ServerKit called ``ConfirmationGate``:

* **Session modes** (per device, default from the profile / settings):
  ``observe`` — write tools are filtered out of the registry entirely (the model never
  sees them); ``supervised`` — write tools pause on the gate and wait for a human to
  approve/deny; ``autonomous`` — the gate auto-approves and logs (for trusted
  automations/CI where no human is watching). Extension write tools are **always** gated
  regardless of mode — third-party code never gets autonomous hardware access.
* **The gate**: when a wrapped write tool is invoked (on the agent's own thread), it
  registers a ``pending_action``, broadcasts it over SSE, and blocks on a
  :class:`threading.Event` until ``confirm_action`` releases it or the deadline passes
  (default-deny on timeout). Approved → run the real tool + audit; denied/timeout → return
  a refusal string the model reads and continues from.
* **Audit**: every write-tool decision (approved / denied / timeout / auto) is persisted to
  ``agent_audit_log`` with who/what/when.

``build_device_tools`` (in ``prompture_agent.py``) does the annotation + wrapping; this
mixin owns the runtime state and decisions so both live where the rest of the agent does.
"""
import time
import logging
import threading

from devicekit.db import session_scope
from devicekit.models import AgentAuditLog

logger = logging.getLogger(__name__)

AGENT_MODES = ("observe", "supervised", "autonomous")
_RESULT_MAX = 4000  # audit result strings are truncated to keep rows bounded


class AgentGateMixin:
    """Runtime state + decisions for the AI agent confirmation gate."""

    _agent_modes = {}          # device_id -> mode
    _pending_actions = {}      # action_id -> action dict (holds a threading.Event)
    _gate_lock = None

    # ------------------------------------------------------------------
    # Session modes
    # ------------------------------------------------------------------
    def _ensure_gate(self):
        if self._gate_lock is None:
            # Class attr default is shared; give this instance its own lock + dicts.
            self._gate_lock = threading.Lock()
            self._agent_modes = {}
            self._pending_actions = {}

    def get_agent_mode(self, device_id):
        """Effective session mode: explicit session override, else the device profile's
        ``agent_mode``, else the settings default (``supervised``)."""
        self._ensure_gate()
        mode = self._agent_modes.get(device_id)
        if mode:
            return mode
        try:
            profile = self.get_profile_by_device(device_id)
            if profile and profile.get("agent_mode") in AGENT_MODES:
                return profile["agent_mode"]
        except Exception:
            pass
        return self.ai_default_agent_mode()

    def set_agent_mode(self, device_id, mode):
        """Set the live session mode for a device. Rebuilds the running agent's tool
        registry when crossing the ``observe`` boundary (observe hides write tools)."""
        if mode not in AGENT_MODES:
            return {"error": f"invalid mode '{mode}'; expected one of {', '.join(AGENT_MODES)}"}
        self._ensure_gate()
        previous = self.get_agent_mode(device_id)
        self._agent_modes[device_id] = mode
        # observe changes which tools the model can even see, so a running conversation
        # needs its registry rebuilt. supervised<->autonomous is read live by the gate.
        if (previous == "observe") != (mode == "observe"):
            self._rebuild_agent_tools(device_id)
        logger.info(f"Agent mode for {device_id}: {previous} -> {mode}")
        return {"device_id": device_id, "mode": mode, "previous": previous}

    def _rebuild_agent_tools(self, device_id):
        conv = self._agent_conversations.get(device_id)
        if not conv:
            return
        from devicekit.mixins.prompture_agent import build_device_tools
        try:
            conv.conversation._tools = build_device_tools(
                self, device_id, mode=self.get_agent_mode(device_id))
        except Exception as e:
            logger.warning(f"Could not rebuild agent tools for {device_id}: {e}")

    # ------------------------------------------------------------------
    # The gate (called on the agent thread from a wrapped write tool)
    # ------------------------------------------------------------------
    def gate_tool_call(self, device_id, tool_name, args, meta, source, real_fn):
        """Mediate one write-tool invocation. Returns the string result the model sees."""
        self._ensure_gate()
        mode = self.get_agent_mode(device_id)
        always_gate = bool(meta.get("always_gate"))

        # observe = read-only: a write reaching the gate here (e.g. a direct caller like
        # self-heal, not a filtered tool) is refused outright and logged.
        if mode == "observe":
            self._audit(device_id, tool_name, args, meta, source, mode,
                        decision=AgentAuditLog.DECISION_DENIED, approver="observe-mode",
                        result=None, error="observe mode: writes not permitted")
            return (f"DENIED: session is in observe (read-only) mode, so '{tool_name}' was "
                    f"NOT performed. Switch to supervised or autonomous to act.")

        # Autonomous auto-approves core tools; extension tools are never autonomous.
        if mode == "autonomous" and not always_gate:
            return self._execute_and_audit(
                device_id, tool_name, args, meta, source, mode,
                decision=AgentAuditLog.DECISION_AUTO, approver="system", real_fn=real_fn)

        action = self._create_pending_action(device_id, tool_name, args, meta, source, mode)
        timeout = self.ai_gate_timeout_seconds()
        released = action["event"].wait(timeout=timeout)
        decision = action.get("decision")
        self._remove_pending_action(action["id"])

        if not released or not decision:
            self._audit(device_id, tool_name, args, meta, source, mode,
                        decision=AgentAuditLog.DECISION_TIMEOUT, approver=None,
                        result=None, error=f"timed out after {timeout}s")
            self._broadcast_resolved(action, AgentAuditLog.DECISION_TIMEOUT, None)
            return (f"DENIED: approval for '{tool_name}' timed out after {timeout}s. "
                    f"The action was NOT performed. Do not retry it; continue or ask the user.")

        if not decision.get("approve"):
            self._audit(device_id, tool_name, args, meta, source, mode,
                        decision=AgentAuditLog.DECISION_DENIED,
                        approver=decision.get("approver"), result=None,
                        error="user denied")
            self._broadcast_resolved(action, AgentAuditLog.DECISION_DENIED,
                                     decision.get("approver"))
            return (f"DENIED: the user declined the '{tool_name}' action. It was NOT "
                    f"performed. Acknowledge this and continue without repeating it.")

        self._broadcast_resolved(action, AgentAuditLog.DECISION_APPROVED,
                                 decision.get("approver"))
        return self._execute_and_audit(
            device_id, tool_name, args, meta, source, mode,
            decision=AgentAuditLog.DECISION_APPROVED,
            approver=decision.get("approver"), real_fn=real_fn)

    def _execute_and_audit(self, device_id, tool_name, args, meta, source, mode,
                           decision, approver, real_fn):
        try:
            result = real_fn(**args)
            result_str = "" if result is None else str(result)
            self._audit(device_id, tool_name, args, meta, source, mode, decision=decision,
                        approver=approver, result=result_str, error=None)
            return result_str
        except Exception as e:
            logger.error(f"Gated tool '{tool_name}' failed on {device_id}: {e}")
            self._audit(device_id, tool_name, args, meta, source, mode, decision=decision,
                        approver=approver, result=None, error=str(e))
            return f"ERROR executing '{tool_name}': {e}"

    # ------------------------------------------------------------------
    # Pending-action registry
    # ------------------------------------------------------------------
    def _create_pending_action(self, device_id, tool_name, args, meta, source, mode):
        import uuid
        now = time.time()
        timeout = self.ai_gate_timeout_seconds()
        action = {
            "id": str(uuid.uuid4()),
            "device_id": device_id,
            "tool": tool_name,
            "label": meta.get("label") or tool_name,
            "category": meta.get("category"),
            "args": args,
            "summary": _summarize_action(meta, tool_name, args),
            "source": source,
            "mode": mode,
            "requested_at": now,
            "deadline": now + timeout,
            "event": threading.Event(),
            "decision": None,
        }
        with self._gate_lock:
            self._pending_actions[action["id"]] = action
        self.broadcast("pending_action", _public_action(action))
        logger.info(f"Pending action {action['id']} on {device_id}: {action['summary']}")
        return action

    def _remove_pending_action(self, action_id):
        with self._gate_lock:
            self._pending_actions.pop(action_id, None)

    def confirm_action(self, action_id, approve, approver=None, device_id=None):
        """Release a blocked gate. Returns a status dict (or an error dict)."""
        self._ensure_gate()
        with self._gate_lock:
            action = self._pending_actions.get(action_id)
        if not action:
            return {"error": "unknown or already-resolved action"}
        if device_id and action["device_id"] != device_id:
            return {"error": "action does not belong to this device"}
        action["decision"] = {"approve": bool(approve), "approver": approver or "unknown"}
        action["event"].set()
        return {"action_id": action_id, "approve": bool(approve), "status": "released"}

    def list_pending_actions(self, device_id=None):
        self._ensure_gate()
        with self._gate_lock:
            actions = list(self._pending_actions.values())
        if device_id:
            actions = [a for a in actions if a["device_id"] == device_id]
        actions.sort(key=lambda a: a["requested_at"])
        return [_public_action(a) for a in actions]

    def _broadcast_resolved(self, action, decision, approver):
        self.broadcast("pending_action_resolved", {
            "id": action["id"],
            "device_id": action["device_id"],
            "tool": action["tool"],
            "decision": decision,
            "approver": approver,
        })

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _audit(self, device_id, tool_name, args, meta, source, mode, decision,
               approver, result, error):
        try:
            with session_scope() as s:
                row = AgentAuditLog(
                    device_id=device_id,
                    tool=tool_name,
                    args=args or {},
                    is_write=bool(meta.get("is_write", True)),
                    category=meta.get("category"),
                    source=source,
                    mode=mode,
                    decision=decision,
                    approver=approver,
                    result=(result[:_RESULT_MAX] if isinstance(result, str) else result),
                    error=error,
                    created_at=time.time(),
                    resolved_at=time.time(),
                )
                s.add(row)
        except Exception as e:  # auditing must never break the agent loop
            logger.warning(f"Failed to write agent audit row for {tool_name}: {e}")

    def audit_agent_action(self, device_id, tool_name, args, decision, source="core",
                           mode=None, approver="system", result=None, error=None,
                           category=None, is_write=True):
        """Public audit hook for actors outside the gate (e.g. self-heal, plan 13 ph3)."""
        self._audit(device_id, tool_name, args,
                    {"is_write": is_write, "category": category}, source,
                    mode or self.get_agent_mode(device_id), decision, approver, result, error)

    def get_agent_audit(self, device_id=None, limit=100):
        with session_scope() as s:
            q = s.query(AgentAuditLog)
            if device_id:
                q = q.filter(AgentAuditLog.device_id == device_id)
            rows = q.order_by(AgentAuditLog.created_at.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]


# --------------------------------------------------------------------------- helpers
def _summarize_action(meta, tool_name, args):
    """Build a short human-readable action summary for the approval card."""
    label = meta.get("label") or tool_name.replace("_", " ")
    if not args:
        return label
    detail = ", ".join(f"{k}={v}" for k, v in args.items())
    return f"{label} ({detail})"


def _public_action(action):
    """Serialize a pending action for SSE / JSON — drops the internal Event/decision."""
    now = time.time()
    return {
        "id": action["id"],
        "device_id": action["device_id"],
        "tool": action["tool"],
        "label": action["label"],
        "category": action["category"],
        "args": action["args"],
        "summary": action["summary"],
        "source": action["source"],
        "mode": action["mode"],
        "requested_at": action["requested_at"],
        "deadline": action["deadline"],
        "seconds_remaining": max(0, round(action["deadline"] - now, 1)),
    }
