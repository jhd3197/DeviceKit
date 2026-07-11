"""Per-device CDP session lifecycle.

A "session" is the durable device-side state — Chrome foregrounded + an ``adb forward`` from a
pooled local port to ``chrome_devtools_remote`` + a recorded row. The CDP WebSocket itself is
opened per operation (see ``cdp.py``), so nothing long-lived can wedge. ``ensure_session`` is
the single idempotent entry every verb goes through, so callers never manage lifecycle.

All device access goes through the permission-gated ``sdk.device_control`` (``adb`` for
forward/shell), keeping the platform gate honest.
"""
import time

from sqlalchemy import select, delete

import devicekit_sdk

from . import cdp
from .cdp import CDPError
from .models import table

SLUG = "devicekit-browser"
log = devicekit_sdk.logger(SLUG)

DEFAULT_PORT_BASE = 9300
DEFAULT_PORT_COUNT = 64
DEFAULT_TIMEOUT = 30


def _config():
    cfg = devicekit_sdk.config(SLUG) or {}
    try:
        base = int(cfg.get("port_base") or DEFAULT_PORT_BASE)
    except (TypeError, ValueError):
        base = DEFAULT_PORT_BASE
    try:
        count = int(cfg.get("port_count") or DEFAULT_PORT_COUNT)
    except (TypeError, ValueError):
        count = DEFAULT_PORT_COUNT
    try:
        timeout = int(cfg.get("cdp_timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    return base, count, timeout


def cdp_timeout():
    return _config()[2]


def _resolve_serial(device_id):
    dev = devicekit_sdk.devices.get(device_id)
    if not dev:
        raise CDPError(f"device '{device_id}' is not connected over adb (browser needs adb)")
    return dev.get("serial") or dev.get("device_id") or device_id


def _alloc_port(s, device_id):
    base, count, _ = _config()
    taken = {
        r.port for r in s.execute(select(table("sessions").c.port)).all()
        if r.port is not None
    }
    for p in range(base, base + count):
        if p not in taken:
            return p
    raise CDPError(f"no free forward port in range {base}-{base + count - 1}")


def _row_to_dict(row):
    if not row:
        return None
    return {
        "device_id": row["device_id"], "serial": row["serial"], "port": row["port"],
        "target_id": row["target_id"], "busy": bool(row["busy"]),
        "created_at": row["created_at"], "last_used": row["last_used"],
    }


def get_session(device_id):
    sessions = table("sessions")
    with devicekit_sdk.db.session() as s:
        row = s.execute(
            select(sessions).where(sessions.c.device_id == device_id)).mappings().first()
        return _row_to_dict(row)


def list_sessions():
    sessions = table("sessions")
    with devicekit_sdk.db.session() as s:
        return [_row_to_dict(r) for r in s.execute(select(sessions)).mappings().all()]


def _ensure_chrome(ctl, device_id):
    installed = ctl.shell(f"pm list packages {cdp.CHROME_PACKAGE}")
    if cdp.CHROME_PACKAGE not in (installed or ""):
        raise CDPError(f"Chrome not available on {device_id} ({cdp.CHROME_PACKAGE} not installed)")
    # Launch Chrome *with* an initial page — a bare LAUNCHER intent can leave Chrome with no
    # drivable page target (empty /json), whereas a VIEW intent guarantees one. The real target
    # is set by the first goto over CDP.
    ctl.shell(f"am start -a android.intent.action.VIEW -d about:blank {cdp.CHROME_PACKAGE}")
    time.sleep(3)


def ensure_session(device_id):
    """Idempotently open (or reuse) a CDP session for ``device_id``. Launches Chrome, sets up
    the adb forward, and pins a dedicated tab. Returns the session dict. Raises
    :class:`CDPError` with a clear message when Chrome/adb is unavailable."""
    serial = _resolve_serial(device_id)
    sessions = table("sessions")
    with devicekit_sdk.db.session() as s:
        row = s.execute(
            select(sessions).where(sessions.c.device_id == device_id)).mappings().first()
        port = row["port"] if row else _alloc_port(s, device_id)
        prev_target = row["target_id"] if row else None

    ctl = devicekit_sdk.device_control(SLUG, device_id)
    try:
        cdp.list_targets(port)
    except CDPError:
        _ensure_chrome(ctl, device_id)
        ctl.forward(port)
        time.sleep(1)
        cdp.list_targets(port)  # re-raises a clear CDPError if still unreachable

    # Reuse the pinned tab if it still exists; otherwise create a fresh dedicated one.
    target_id = prev_target if cdp.target_exists(port, prev_target) else cdp.create_target(port)

    now = time.time()
    with devicekit_sdk.db.session() as s:
        existing = s.execute(
            select(sessions).where(sessions.c.device_id == device_id)).mappings().first()
        if existing:
            s.execute(sessions.update().where(sessions.c.device_id == device_id).values(
                serial=serial, port=port, target_id=target_id, last_used=now))
        else:
            s.execute(sessions.insert().values(
                device_id=device_id, serial=serial, port=port, target_id=target_id,
                busy=0, created_at=now, last_used=now))
    devicekit_sdk.broadcast("extension_event",
                            {"slug": SLUG, "kind": "session_open", "device_id": device_id})
    return get_session(device_id)


def close_session(device_id):
    """Close the dedicated tab, tear down the adb forward, and drop the session row.
    Best-effort throughout."""
    sess = get_session(device_id)
    sessions = table("sessions")
    if sess and sess.get("port"):
        try:
            cdp.close_target(sess["port"], sess.get("target_id"))
        except Exception as e:
            log.warning(f"close_target failed for {device_id}: {e}")
        try:
            devicekit_sdk.device_control(SLUG, device_id).remove_forward(sess["port"])
        except Exception as e:
            log.warning(f"remove_forward failed for {device_id}: {e}")
    with devicekit_sdk.db.session() as s:
        s.execute(delete(sessions).where(sessions.c.device_id == device_id))
    devicekit_sdk.broadcast("extension_event",
                            {"slug": SLUG, "kind": "session_close", "device_id": device_id})
    return {"closed": bool(sess), "device_id": device_id}


def set_busy(device_id, busy):
    sessions = table("sessions")
    with devicekit_sdk.db.session() as s:
        s.execute(sessions.update().where(sessions.c.device_id == device_id).values(
            busy=1 if busy else 0))


def touch(device_id):
    sessions = table("sessions")
    with devicekit_sdk.db.session() as s:
        s.execute(sessions.update().where(sessions.c.device_id == device_id).values(
            last_used=time.time()))


def session_context(device_id):
    """Ensure a session and return ``(port, target_id)`` — the entry point for every verb."""
    sess = ensure_session(device_id)
    touch(device_id)
    return sess["port"], sess["target_id"]
