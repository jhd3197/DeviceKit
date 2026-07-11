"""Notification capture core: poll the agent notification listener, dedupe into the events
table, forward matches onto the plan-06 bus, and block for a matching notification (OTP/2FA).

Reaching the on-device agent (its ``GET /notifications`` feed) needs the host's
``find_agent_device`` + ``_agent_device_states`` — accessed through ``devicekit_sdk.get_host()``,
the same path core's file routes use. Capability advertisement is tolerant of the agent
reporting ``capabilities`` as either a list or a map.
"""
import re
import time
import uuid
import hashlib

import requests
from sqlalchemy import select, delete, insert

import devicekit_sdk

from .models import events_table

SLUG = "devicekit-notification-capture"
log = devicekit_sdk.logger(SLUG)

CAPTURED_EVENT = "notification.captured"


# --------------------------------------------------------------------------- config
def _config():
    cfg = devicekit_sdk.config(SLUG) or {}
    allow_raw = cfg.get("package_allowlist") or ""
    if isinstance(allow_raw, str):
        allow = [p.strip() for p in allow_raw.split(",") if p.strip()]
    else:
        allow = [str(p) for p in (allow_raw or [])]
    regex_raw = cfg.get("regex_filter") or ""
    try:
        regex = re.compile(regex_raw) if regex_raw else None
    except re.error:
        log.warning("Invalid regex_filter %r — ignoring", regex_raw)
        regex = None
    try:
        retention = int(cfg.get("retention_days") or 7)
    except (TypeError, ValueError):
        retention = 7
    return {
        "package_allowlist": allow,
        "regex": regex,
        "retention_days": retention,
        "forward_to_bus": bool(cfg.get("forward_to_bus")),
    }


# --------------------------------------------------------------------------- agent access
def _agent_base(device_id):
    host = devicekit_sdk.get_host()
    if host is None or not hasattr(host, "find_agent_device"):
        return None
    try:
        agent = host.find_agent_device(device_id)
    except Exception:
        return None
    if not agent or not agent.get("online"):
        return None
    info = agent.get("info") or {}
    ip = info.get("ip")
    port = info.get("agent_port", 9800)
    return f"http://{ip}:{port}" if ip else None


def _has_listener(state):
    caps = state.get("capabilities") or {}
    if isinstance(caps, dict):
        return bool(caps.get("notification_listener"))
    if isinstance(caps, (list, tuple, set)):
        return "notification_listener" in caps
    return False


def capable_devices():
    """device_ids of online agents advertising the notification-listener capability."""
    host = devicekit_sdk.get_host()
    states = getattr(host, "_agent_device_states", None) or {}
    out = []
    for did, st in list(states.items()):
        if st.get("online") and _has_listener(st):
            out.append(st.get("device_id") or did)
    return out


def fetch_notifications(device_id):
    """The agent's recent notification feed as a list of ``{package,title,text,timestamp}``."""
    base = _agent_base(device_id)
    if not base:
        return []
    try:
        r = requests.get(f"{base}/notifications", timeout=6)
        if not r.ok:
            return []
        return (r.json() or {}).get("notifications", [])
    except Exception as e:
        log.debug("fetch_notifications(%s) failed: %s", device_id, e)
        return []


def _dedup_key(device_id, n):
    raw = f"{device_id}|{n.get('package')}|{n.get('timestamp')}|{n.get('title')}|{n.get('text')}"
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


# --------------------------------------------------------------------------- persistence
def _exists(key):
    ev = events_table()
    with devicekit_sdk.db.session() as s:
        return s.execute(
            select(ev.c.id).where(ev.c.dedup_key == key).limit(1)).first() is not None


def _record(device_id, pkg, title, text, posted_at, key):
    ev = events_table()
    with devicekit_sdk.db.session() as s:
        s.execute(insert(ev).values(
            id=str(uuid.uuid4()), device_id=device_id, package=pkg,
            title=(title or "")[:500], text=(text or "")[:2000],
            posted_at=posted_at, dedup_key=key, captured_at=time.time()))


def _prune(retention_days):
    ev = events_table()
    cutoff = time.time() - retention_days * 86400
    with devicekit_sdk.db.session() as s:
        s.execute(delete(ev).where(ev.c.captured_at < cutoff))


def recent(device_id=None, limit=50):
    ev = events_table()
    q = select(ev).order_by(ev.c.captured_at.desc()).limit(limit)
    if device_id:
        q = select(ev).where(ev.c.device_id == device_id).order_by(ev.c.captured_at.desc()).limit(limit)
    with devicekit_sdk.db.session() as s:
        rows = s.execute(q).mappings().all()
    return [{
        "id": r["id"], "device_id": r["device_id"], "package": r["package"],
        "title": r["title"], "text": r["text"], "posted_at": r["posted_at"],
        "captured_at": r["captured_at"],
    } for r in rows]


def _forward(device_id, pkg, title, text):
    devicekit_sdk.notify.send(
        CAPTURED_EVENT,
        data={"package": pkg, "title": title, "text": text, "device_id": device_id},
        subject_type="device", subject_id=device_id, severity="info")


# --------------------------------------------------------------------------- poll job
def poll(job):
    """Scheduled poll handler (plan 05). Polls each capable device's notification feed,
    records new items (deduped + filtered), forwards matches onto the bus, prunes old rows.
    Returns a summary dict."""
    cfg = _config()
    allow, regex = cfg["package_allowlist"], cfg["regex"]
    devices = capable_devices()
    captured = 0
    for device_id in devices:
        for n in fetch_notifications(device_id):
            pkg = n.get("package") or ""
            if allow and pkg not in allow:
                continue
            title, text = n.get("title") or "", n.get("text") or ""
            if regex and not regex.search(f"{title}\n{text}"):
                continue
            key = _dedup_key(device_id, n)
            if _exists(key):
                continue
            _record(device_id, pkg, title, text, n.get("timestamp"), key)
            captured += 1
            if cfg["forward_to_bus"]:
                try:
                    _forward(device_id, pkg, title, text)
                except Exception as e:
                    log.warning("bus forward failed: %s", e)
    if captured or devices:
        _prune(cfg["retention_days"])
    return {"captured": captured, "devices": len(devices)}


# --------------------------------------------------------------------------- wait / OTP
def wait_for_match(device_id, pattern, package=None, timeout=60):
    """Block up to ``timeout`` seconds for a NEW notification matching ``pattern`` (regex on
    title+text). Returns the first capture group if the pattern has one, else the whole match,
    or ``None`` on timeout.

    A baseline snapshot of already-present notifications is taken up front so only *newly
    arrived* ones match — robust against the phone/host clock skew that makes timestamp
    comparison unreliable."""
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid pattern: {e}")
    deadline = time.time() + max(1, timeout)
    baseline = {_dedup_key(device_id, n) for n in fetch_notifications(device_id)}
    while time.time() < deadline:
        for n in fetch_notifications(device_id):
            key = _dedup_key(device_id, n)
            if key in baseline:
                continue
            if package and (n.get("package") or "") != package:
                continue
            hay = f"{n.get('title') or ''}\n{n.get('text') or ''}"
            m = rx.search(hay)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        time.sleep(1.5)
    return None
