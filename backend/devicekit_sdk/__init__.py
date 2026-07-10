"""``devicekit_sdk`` — the stable façade extensions import instead of host internals
(plan 03; port of ServerKit's ``plugins_sdk``).

An extension's backend imports from here (``from devicekit_sdk import db, logger, devices,
register_step_type, ...``) and never reaches into ``devicekit.*``. The host wires itself in
at boot via :func:`set_host`; every façade call routes to the live ``Client`` composite.

Exports: ``db`` (Base + session), ``logger``, ``config``, ``broadcast``, ``devices``
(read-only fleet accessors), ``device_control`` (permission-gated adb/input),
``register_step_type``, ``register_fql_field``, ``ai`` (AI-tool binder), ``jobs``/``notify``
(plans 05/06 seams), ``permissions`` / ``require_permission``, ``devicekit_version``.
"""
import logging
from contextlib import contextmanager

from devicekit import __version__ as _DK_VERSION
from devicekit import db as _db
from devicekit_sdk import permissions
from devicekit_sdk.permissions import PermissionDenied

require_permission = permissions.require

# The live host (Client composite). Set once at boot by ExtensionsMixin.init_extensions().
_host = None
# Slug currently being activated — lets register_* attribute contributions for teardown.
_current_slug = None


def set_host(client):
    global _host
    _host = client


def get_host():
    return _host


@contextmanager
def _activating(slug):
    """Scope register_* calls to ``slug`` so the host can deregister them on disable."""
    global _current_slug
    prev = _current_slug
    _current_slug = slug
    try:
        yield
    finally:
        _current_slug = prev


def devicekit_version():
    return _DK_VERSION


# --------------------------------------------------------------------------- db
class _Db:
    """Persistence seam: extensions declare models on ``db.Base`` (shared metadata) and use
    ``with db.session() as s:`` for a short-lived transactional session."""

    @property
    def Base(self):
        return _db.Base

    def session(self):
        return _db.session_scope()

    @property
    def engine(self):
        return _db.get_engine()

    def create_all(self):
        _db.create_all()


db = _Db()


def logger(name):
    """A namespaced logger for an extension (``logger(slug)``)."""
    return logging.getLogger(f"devicekit.ext.{name}")


def config(slug):
    """The extension's saved config (including secrets — this is the in-process view the
    extension needs, unlike the masked API response)."""
    if _host is None:
        return {}
    return _host.get_extension_config_raw(slug)


def broadcast(event_type, data):
    """Push an SSE event to all connected clients."""
    if _host is not None:
        _host.broadcast(event_type, data)


# ---------------------------------------------------------------------- devices
class _Devices:
    """Read-only fleet accessors."""

    def list(self):
        return _host.get_devices() if _host else []

    def get(self, device_id):
        try:
            return _host.get_device(device_id) if _host else None
        except Exception:
            return None


devices = _Devices()


class _DeviceControl:
    """Permission-gated device control (adb / input). Requires the extension to have
    declared ``device.control`` (or ``adb`` for raw shell)."""

    def __init__(self, slug, device_id):
        self._slug = slug
        self._device_id = device_id

    def tap(self, x, y):
        require_permission(self._slug, "device.control")
        return _host.click(x, y, self._device_id)

    def press(self, key):
        require_permission(self._slug, "device.control")
        return _host.press_action(key, self._device_id)

    def screenshot(self):
        require_permission(self._slug, "device.control")
        return _host.take_screenshot(self._device_id)

    def shell(self, command):
        require_permission(self._slug, "adb")
        return _host.run_adb_command(f"shell {command}", device=self._device_id)


def device_control(slug, device_id):
    return _DeviceControl(slug, device_id)


# ----------------------------------------------------------- contribution points
def register_step_type(type_name, spec):
    """Register an automation step type (tracked for teardown on disable/uninstall)."""
    _host.register_step_type(type_name, spec)
    if _current_slug is not None:
        _host._track_contribution(_current_slug, "step_types", type_name)


def register_fql_field(name, spec):
    """Register a fleet-query field (tracked for teardown on disable/uninstall)."""
    _host.register_fql_field(name, spec)
    if _current_slug is not None:
        _host._track_contribution(_current_slug, "fql_fields", name)


class _AiBinder:
    """Passed to an extension's ``ai_tools`` register function; collects tools that get
    bound (namespaced ``<slug>__<name>``) into every per-device Prompture ToolRegistry."""

    def __init__(self, slug):
        self._slug = slug

    def tool(self, func):
        name = getattr(func, "__name__", "tool")
        description = (func.__doc__ or "").strip() or None
        _host._register_ai_tool(self._slug, name, func, description)
        return func


def ai(slug):
    return _AiBinder(slug)


# --------------------------------------------------------------------------- jobs
class _Jobs:
    """Background-work seam (plan 05). Extensions enqueue durable work, register their own
    job kinds, and declare periodic schedules — all riding the host's unified job system.

    Handlers and schedules registered during activation are tracked against the current
    slug so ``disable``/``uninstall`` can tear them down (schedules pause as a set via the
    host's ``pause_jobs``)."""

    def enqueue(self, kind, payload=None, max_attempts=3, priority=0, delay_ms=0,
                owner_type=None, owner_id=None):
        return _host.enqueue_job(
            kind, payload=payload, max_attempts=max_attempts, priority=priority,
            delay_ms=delay_ms, owner_type=owner_type, owner_id=owner_id)

    def register(self, kind, handler, replace=True):
        """Register a ``kind → handler(job_dict) -> result`` mapping (tracked for teardown)."""
        _host.register_job_kind(kind, handler, replace=replace)
        if _current_slug is not None:
            _host._track_contribution(_current_slug, "job_kinds", kind)

    def schedule(self, name, kind, interval_seconds=None, cron=None, payload=None,
                 max_attempts=1, startup_delay_seconds=0):
        """Idempotently declare a periodic schedule owned by this extension so the host can
        pause/resume every schedule for the extension together on disable/enable."""
        return _host.ensure_scheduled_job(
            name, kind, interval_seconds=interval_seconds, cron=cron, payload=payload,
            max_attempts=max_attempts, startup_delay_seconds=startup_delay_seconds,
            owner_type="extension", owner_id=_current_slug)

    def get(self, job_id):
        return _host.get_job(job_id)

    def list(self, **kwargs):
        return _host.list_jobs(**kwargs)


jobs = _Jobs()


class _Unavailable:
    def __init__(self, what):
        self._what = what

    def __getattr__(self, _name):
        raise NotImplementedError(f"{self._what} SDK is not available yet (see roadmap)")


notify = _Unavailable("notify")

__all__ = [
    "set_host", "get_host", "devicekit_version",
    "db", "logger", "config", "broadcast",
    "devices", "device_control",
    "register_step_type", "register_fql_field", "ai",
    "jobs", "notify",
    "permissions", "require_permission", "PermissionDenied",
]
