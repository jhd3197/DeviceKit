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
from devicekit.agent_capabilities import supports_batch_survey

logger = logging.getLogger(__name__)

SURVEY_COMMAND_PREFIX = "survey."
# One-shot command that carries a whole probe recipe (capability-gated optimization).
SURVEY_BATCH_COMMAND = "survey.batch"


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
        """Run a named composed probe, negotiating the transport by capability.

        A ``batch_survey``-capable agent gets the whole probe in one ``survey.batch`` command
        (one round trip). Every other agent — and any agent whose batch attempt fails or
        returns malformed data — falls back to the per-primitive composed path from phase 1,
        which works forever. Either way the return shape is identical.
        """
        recipe = get_probe(probe)  # raises PrimitiveError on an unknown probe
        caps = (self.get_agent_capabilities(device_id)
                if hasattr(self, "get_agent_capabilities") else {})
        if supports_batch_survey(caps):
            batched = self._batched_probe(device_id, probe, recipe, timeout)
            if batched is not None:
                return batched
            logger.info("Batched survey failed for %s; falling back to composed", device_id)
        return self._composed_probe(device_id, probe, recipe, timeout)

    def _composed_probe(self, device_id, probe, recipe, timeout):
        """Permanent fallback: one command per primitive, folded into one result."""
        steps = []
        ok = True
        for step in recipe:
            row = self.send_device_command(
                device_id, f"{SURVEY_COMMAND_PREFIX}{step['primitive']}",
                args=step["args"], timeout=timeout, source="survey") or {}
            step_ok = row.get("status") == "completed"
            ok = ok and step_ok
            steps.append({
                "primitive": step["primitive"],
                "args": step["args"],
                "status": row.get("status"),
                "result": row.get("result"),
                "error": row.get("error"),
            })
        return {"device_id": device_id, "probe": probe, "ok": ok,
                "transport": "composed", "steps": steps}

    def _batched_probe(self, device_id, probe, recipe, timeout):
        """Capability-gated optimization: send the whole recipe in one command.

        Returns the folded result, or ``None`` to signal the caller to fall back to the
        composed path (agent offline, command failed, or a result the agent couldn't parse
        into per-primitive rows).
        """
        payload = {"primitives": [{"primitive": s["primitive"], "args": s["args"]}
                                  for s in recipe]}
        row = self.send_device_command(
            device_id, SURVEY_BATCH_COMMAND, args=payload, timeout=timeout,
            source="survey") or {}
        if row.get("status") != "completed":
            return None
        result = row.get("result") or {}
        results = result.get("results")
        if not isinstance(results, list):
            return None  # agent returned something we can't fold — fall back
        by_primitive = {}
        for r in results:
            if isinstance(r, dict) and r.get("primitive"):
                by_primitive[r["primitive"]] = r
        steps = []
        ok = True
        for step in recipe:
            r = by_primitive.get(step["primitive"], {})
            step_ok = not r.get("error") and "result" in r
            ok = ok and step_ok
            steps.append({
                "primitive": step["primitive"],
                "args": step["args"],
                "status": "completed" if step_ok else "failed",
                "result": r.get("result"),
                "error": r.get("error"),
            })
        return {"device_id": device_id, "probe": probe, "ok": ok,
                "transport": "batched", "steps": steps}
