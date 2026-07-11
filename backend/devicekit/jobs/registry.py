"""In-process registry mapping a job ``kind`` to its handler (port of ServerKit's
``jobs/registry.py``).

A handler is a callable ``fn(job) -> result`` where ``job`` is a plain dict snapshot of the
Job row (id, kind, payload, attempts, owner_*). The return value (JSON-serializable, or
``None``) is stored as the job result. Raising propagates to the consumer, which records the
error and lets the Queue Bus retry / dead-letter.

DeviceKit handlers are typically closures bound to the ``Client`` composite (so they can
drive devices), registered by ``JobsMixin`` at boot — but any callable works, which is what
lets an extension contribute a job kind through the SDK.
"""
import logging

logger = logging.getLogger(__name__)

_HANDLERS = {}


def register(kind, handler, replace=False):
    """Register ``handler`` for ``kind``. Existing kinds are kept unless ``replace=True``
    (so a re-register on extension reload is clean)."""
    if not kind or not callable(handler):
        raise ValueError("register(kind, handler): kind required and handler must be callable")
    if kind in _HANDLERS and not replace:
        logger.debug("Job handler for %r already registered; keeping existing", kind)
        return
    _HANDLERS[kind] = handler


def handler(kind, replace=False):
    """Decorator form of :func:`register`."""
    def _decorator(fn):
        register(kind, fn, replace=replace)
        return fn
    return _decorator


def unregister(kind):
    _HANDLERS.pop(kind, None)


def get(kind):
    return _HANDLERS.get(kind)


def is_registered(kind):
    return kind in _HANDLERS


def registered_kinds():
    return sorted(_HANDLERS.keys())


def clear():
    """Test helper — drop all registered handlers."""
    _HANDLERS.clear()
