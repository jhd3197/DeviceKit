"""AgentSurveyMixin — compose read-only survey primitives over the command channel (plan 25).

The server never pushes a shell command to a device. It dispatches **allowlisted read-only
primitives** (``devicekit.agent_primitives``) through the same reconnect-aware command
transport plan 07 built (``send_device_command``), namespaced ``survey.<primitive>`` so the
on-device dispatcher can route them to its own fixed executor and refuse anything else.

Two entry points:
* ``send_agent_primitive`` — one validated primitive → one ``DeviceCommand`` row.
* ``compose_agent_probe`` — a named recipe of primitives, run in order and combined into a
  single survey result (the "server composes" side of the trust boundary).

Composed is the *permanent fallback*. Plan 25 phase 2 adds a batched single-round-trip probe
as a capability-gated optimization on top; this composed path always works, even for the
oldest agent that speaks nothing but the primitive set.
"""
import logging

from devicekit.agent_primitives import (
    validate_primitive, get_probe, list_primitives, PrimitiveError)

logger = logging.getLogger(__name__)

SURVEY_COMMAND_PREFIX = "survey."


class AgentSurveyMixin:
    """Compose read-only survey primitives; never name a raw command."""

    def list_agent_primitives(self):
        """The allowlist catalog (primitives + composed probes) for the panel/API."""
        return list_primitives()

    def send_agent_primitive(self, device_id, primitive, args=None, timeout=None):
        """Validate one primitive and dispatch it to the agent, blocking for the result.

        Raises ``PrimitiveError`` before any dispatch if ``primitive`` is off the allowlist
        or the args are malformed — the request never reaches the device as a raw command.
        Returns the ``DeviceCommand`` row (``send_device_command`` semantics: an offline
        device yields a ``failed``/``AGENT_OFFLINE`` row rather than hanging).
        """
        norm = validate_primitive(primitive, args or {})
        return self.send_device_command(
            device_id, f"{SURVEY_COMMAND_PREFIX}{primitive}", args=norm,
            timeout=timeout, source="survey")

    def compose_agent_probe(self, device_id, probe, timeout=None):
        """Run a named composed probe: each step is an allowlisted primitive, dispatched in
        order and folded into one result. A step that fails is recorded (not raised) so the
        probe returns partial evidence instead of aborting — the composer's job is to
        *combine* primitives, and a missing package or offline moment is data, not a crash.
        """
        recipe = get_probe(probe)  # raises PrimitiveError on an unknown probe
        steps = []
        ok = True
        for step in recipe:
            row = self.send_device_command(
                device_id, f"{SURVEY_COMMAND_PREFIX}{step['primitive']}",
                args=step["args"], timeout=timeout, source="survey")
            row = row or {}
            step_ok = row.get("status") == "completed"
            ok = ok and step_ok
            steps.append({
                "primitive": step["primitive"],
                "args": step["args"],
                "status": row.get("status"),
                "result": row.get("result"),
                "error": row.get("error"),
            })
        return {"device_id": device_id, "probe": probe, "ok": ok, "steps": steps}
