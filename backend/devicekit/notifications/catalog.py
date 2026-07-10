"""Event catalog — the single source of truth for what a notification *is* (plan 06).

An entry maps an ``event_key`` to its rendered shape: a ``title`` template, a ``severity``
(``info`` | ``warning`` | ``critical``), a ``category`` (used for grouping / icon choice), an
optional ``body`` template, and a ``deep_link`` template pointing at the subject in the UI.
Templates are plain ``str.format`` strings rendered against the event ``data`` dict — a
missing key renders empty rather than raising, so a producer that forgets a field degrades
gracefully instead of dropping the notification.

Adding an alert type is a :func:`register` call (or a seed entry below), never new code.
Extensions register through the SDK (``sdk.notify.register_event(...)``), which routes here.
"""
import logging
from string import Formatter

logger = logging.getLogger(__name__)

SEVERITIES = ("info", "warning", "critical")


class _SafeDict(dict):
    """Missing keys render as an empty string instead of raising KeyError."""

    def __missing__(self, key):
        return ""


def _render(template, data):
    if not template:
        return ""
    try:
        return Formatter().vformat(template, (), _SafeDict(data or {}))
    except Exception:
        # A malformed template must never sink a notification.
        return template


class EventDefinition:
    """One catalog entry. Immutable-ish; ``render_*`` produce the persisted strings."""

    def __init__(self, event_key, title, severity="info", category="general",
                 body="", deep_link=""):
        if severity not in SEVERITIES:
            severity = "info"
        self.event_key = event_key
        self.title = title
        self.severity = severity
        self.category = category
        self.body = body
        self.deep_link = deep_link

    def render_title(self, data):
        return _render(self.title, data) or self.event_key

    def render_body(self, data):
        return _render(self.body, data)

    def render_deep_link(self, data):
        return _render(self.deep_link, data)

    def to_dict(self):
        return {
            "event_key": self.event_key,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "body": self.body,
            "deep_link": self.deep_link,
        }


_CATALOG = {}


def register(event_key, title, severity="info", category="general", body="",
             deep_link="", replace=True):
    """Register (or replace) a catalog entry. Returns the stored definition."""
    if not event_key or not title:
        raise ValueError("register(event_key, title): both are required")
    if event_key in _CATALOG and not replace:
        return _CATALOG[event_key]
    _CATALOG[event_key] = EventDefinition(
        event_key, title, severity=severity, category=category, body=body, deep_link=deep_link)
    return _CATALOG[event_key]


def unregister(event_key):
    _CATALOG.pop(event_key, None)


def get(event_key):
    """Return the definition for ``event_key``, or a permissive fallback so an unseeded
    event still produces a sensible notification (title == the key)."""
    entry = _CATALOG.get(event_key)
    if entry is not None:
        return entry
    logger.debug("Notification event %r not in catalog; using fallback", event_key)
    return EventDefinition(event_key, title=event_key, severity="info", category="general")

def has(event_key):
    return event_key in _CATALOG


def all_events():
    return [e.to_dict() for e in sorted(_CATALOG.values(), key=lambda e: e.event_key)]


def clear():
    """Test helper — drop every registered entry."""
    _CATALOG.clear()


# ---------------------------------------------------------------------------
# Seed: DeviceKit's real fleet events. Deep links target existing, stable routes
# (/devices/<id>, /automations, /pipeline) so they survive frontend refactors.
# ---------------------------------------------------------------------------
def seed_default_events():
    """Idempotently register DeviceKit's built-in events. Called by NotificationsMixin at
    boot; safe to call repeatedly."""
    register("device.offline",
             "{device_name} went offline", severity="warning", category="device",
             body="No heartbeat received from {device_id}.",
             deep_link="/devices/{device_id}")
    register("device.online",
             "{device_name} is back online", severity="info", category="device",
             deep_link="/devices/{device_id}")
    register("device.battery.critical",
             "{device_name} battery critical ({level}%)", severity="critical", category="device",
             body="Battery level is {level}%.",
             deep_link="/devices/{device_id}")
    register("device.storage.low",
             "{device_name} storage low ({free_pct}% free)", severity="warning", category="device",
             body="Only {free_mb} MB remaining.",
             deep_link="/devices/{device_id}")
    register("automation.run.failed",
             "Automation '{automation_name}' failed", severity="critical", category="automation",
             body="Step {step_index} ({step_type}) failed: {error}",
             deep_link="/automations")
    register("automation.run.healed",
             "Automation '{automation_name}' self-healed a step", severity="info",
             category="automation",
             body="Step {step_index} recovered automatically: {heal_reasoning}",
             deep_link="/automations")
    register("regression.detected",
             "Visual regression in '{automation_name}'", severity="warning", category="regression",
             body="Baseline similarity {similarity}% below threshold on {device_name}.",
             deep_link="/automations")
    register("bundle.created",
             "Debug bundle captured for {device_name}", severity="info", category="debug",
             body="Trigger: {trigger}.",
             deep_link="/devices/{device_id}")
    register("pipeline.build.failed",
             "Pipeline build {build_id} failed", severity="critical", category="pipeline",
             deep_link="/pipeline")
    register("agent.enrolled",
             "New agent enrolled: {device_name}", severity="info", category="fleet",
             body="{device_id} registered with the fleet.",
             deep_link="/devices/{device_id}")
