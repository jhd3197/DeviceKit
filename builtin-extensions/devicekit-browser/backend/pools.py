"""Pool routing — treat N devices as one browser farm.

A pool is a named device set + a dispatch strategy. Membership is an explicit serial list,
``all``, or an FQL query (re-evaluated on every dispatch, so devices join/leave as their state
changes). Strategies: ``round_robin`` (cursor persisted in the pool row → survives restart),
``random``, ``least_recently_used``. Concurrency is 1 per device, so a device with an active
session is skipped, not queued; a device that fails to connect is put on a short cooldown and
the next device is tried transparently. ``sticky`` tokens pin a multi-step flow to one device.
"""
import json
import time
import uuid
import random

from sqlalchemy import select

import devicekit_sdk

from . import sessions
from .models import table

SLUG = "devicekit-browser"
log = devicekit_sdk.logger(SLUG)

STRATEGIES = ("round_robin", "random", "least_recently_used")
DEFAULT_STICKY_TTL = 600          # seconds a sticky token pins a device before it times out
UNHEALTHY_COOLDOWN = 60           # seconds a device is skipped after a connect failure

# Transient per-process health cooldown (device_id -> until_ts). Cooldowns are short-lived, so
# they intentionally do not survive a restart.
_unhealthy = {}


class PoolError(Exception):
    pass


# --------------------------------------------------------------------------- pool CRUD
def _pool_to_dict(row):
    if not row:
        return None
    return {
        "name": row["name"], "spec_type": row["spec_type"],
        "spec_value": row["spec_value"], "strategy": row["strategy"],
        "cursor": row["cursor"] or 0,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _parse_spec(spec):
    """Normalize a create request into (spec_type, spec_value)."""
    if spec.get("all"):
        return "all", ""
    if spec.get("fql"):
        return "fql", str(spec["fql"])
    devices = spec.get("devices")
    if devices:
        if not isinstance(devices, list):
            raise PoolError("'devices' must be a list of serials")
        return "list", json.dumps(devices)
    raise PoolError("pool needs one of: devices (list), fql (string), or all=true")


def create_pool(name, spec, strategy="round_robin"):
    if not name:
        raise PoolError("pool name is required")
    if strategy not in STRATEGIES:
        raise PoolError(f"strategy must be one of {list(STRATEGIES)}")
    spec_type, spec_value = _parse_spec(spec or {})
    pools = table("pools")
    now = time.time()
    with devicekit_sdk.db.session() as s:
        existing = s.execute(select(pools).where(pools.c.name == name)).mappings().first()
        if existing:
            s.execute(pools.update().where(pools.c.name == name).values(
                spec_type=spec_type, spec_value=spec_value, strategy=strategy, updated_at=now))
        else:
            s.execute(pools.insert().values(
                name=name, spec_type=spec_type, spec_value=spec_value, strategy=strategy,
                cursor=0, created_at=now, updated_at=now))
    return get_pool(name)


def get_pool(name):
    pools = table("pools")
    with devicekit_sdk.db.session() as s:
        return _pool_to_dict(
            s.execute(select(pools).where(pools.c.name == name)).mappings().first())


def list_pools():
    pools = table("pools")
    with devicekit_sdk.db.session() as s:
        return [_pool_to_dict(r) for r in s.execute(select(pools)).mappings().all()]


def delete_pool(name):
    from sqlalchemy import delete
    pools = table("pools")
    with devicekit_sdk.db.session() as s:
        s.execute(delete(pools).where(pools.c.name == name))
    return {"deleted": True, "name": name}


# --------------------------------------------------------------------------- membership
def _all_device_ids():
    ids = []
    for d in devicekit_sdk.devices.list():
        did = d.get("device_id") or d.get("serial")
        if did:
            ids.append(did)
    return ids


def resolve_members(pool):
    """Resolve a pool's current membership to a list of device_ids. FQL is re-evaluated here,
    so the rotation reflects live device state on every dispatch."""
    spec_type = pool["spec_type"]
    if spec_type == "all":
        return _all_device_ids()
    if spec_type == "list":
        try:
            serials = json.loads(pool["spec_value"] or "[]")
        except json.JSONDecodeError:
            serials = []
        connected = set(_all_device_ids())
        # Keep declared order; only include devices that are actually connected.
        return [x for x in serials if x in connected] or serials
    if spec_type == "fql":
        host = devicekit_sdk.get_host()
        devs = list(devicekit_sdk.devices.list())
        try:
            matches = host.execute_fleet_query(pool["spec_value"], devices=devs)
        except Exception as e:
            raise PoolError(f"FQL evaluation failed: {e}")
        return [d.get("device_id") or d.get("serial") for d in matches if (d.get("device_id") or d.get("serial"))]
    return []


# --------------------------------------------------------------------------- health / busy
def mark_unhealthy(device_id, cooldown=UNHEALTHY_COOLDOWN):
    _unhealthy[device_id] = time.time() + cooldown


def is_healthy(device_id):
    until = _unhealthy.get(device_id, 0)
    if until and time.time() < until:
        return False
    if until:
        _unhealthy.pop(device_id, None)
    return True


def _busy_device_ids():
    s_tbl = table("sessions")
    with devicekit_sdk.db.session() as s:
        rows = s.execute(select(s_tbl.c.device_id, s_tbl.c.busy)).all()
    return {r.device_id for r in rows if r.busy}


def _last_used_map():
    s_tbl = table("sessions")
    with devicekit_sdk.db.session() as s:
        rows = s.execute(select(s_tbl.c.device_id, s_tbl.c.last_used)).all()
    return {r.device_id: (r.last_used or 0) for r in rows}


# --------------------------------------------------------------------------- dispatch
def _advance_cursor(name, value):
    pools = table("pools")
    with devicekit_sdk.db.session() as s:
        s.execute(pools.update().where(pools.c.name == name).values(cursor=value, updated_at=time.time()))


def pick_device(pool, exclude=None):
    """Pick the next available device from a pool per its strategy. Skips busy and cooled-down
    devices (and anything in ``exclude`` — used by failover retries). Returns a device_id or
    raises :class:`PoolError` when nothing is available."""
    exclude = set(exclude or ())
    members = resolve_members(pool)
    if not members:
        raise PoolError(f"pool '{pool['name']}' has no members")
    busy = _busy_device_ids()

    def available(did):
        return did not in exclude and did not in busy and is_healthy(did)

    candidates = [m for m in members if available(m)]
    if not candidates:
        raise PoolError(f"pool '{pool['name']}' has no available device (all busy/offline/cooling down)")

    strategy = pool["strategy"]
    if strategy == "random":
        return random.choice(candidates)
    if strategy == "least_recently_used":
        lru = _last_used_map()
        return min(candidates, key=lambda d: lru.get(d, 0))
    # round_robin (default): rotate over the full member list starting at the cursor.
    start = (pool["cursor"] or 0) % len(members)
    n = len(members)
    for i in range(n):
        pos = (start + i) % n
        did = members[pos]
        if available(did):
            _advance_cursor(pool["name"], pos + 1)
            return did
    return candidates[0]


def pool_status(pool):
    members = resolve_members(pool)
    busy = _busy_device_ids()
    lru = _last_used_map()
    devices = []
    for did in members:
        devices.append({
            "device_id": did,
            "busy": did in busy,
            "healthy": is_healthy(did),
            "last_used": lru.get(did, 0),
        })
    return {
        "name": pool["name"], "strategy": pool["strategy"],
        "spec_type": pool["spec_type"], "cursor": pool["cursor"] or 0,
        "rotation": members, "devices": devices,
    }


# --------------------------------------------------------------------------- sticky tokens
def create_sticky(device_id, pool_name, ttl=DEFAULT_STICKY_TTL):
    sticky = table("sticky")
    token = uuid.uuid4().hex
    now = time.time()
    with devicekit_sdk.db.session() as s:
        s.execute(sticky.insert().values(
            token=token, device_id=device_id, pool=pool_name,
            created_at=now, expires_at=now + ttl))
    return token


def resolve_sticky(token):
    sticky = table("sticky")
    with devicekit_sdk.db.session() as s:
        row = s.execute(select(sticky).where(sticky.c.token == token)).mappings().first()
    if not row:
        return None
    if row["expires_at"] and time.time() > row["expires_at"]:
        release_sticky(token)
        return None
    return {"token": token, "device_id": row["device_id"], "pool": row["pool"],
            "expires_at": row["expires_at"]}


def release_sticky(token):
    from sqlalchemy import delete
    sticky = table("sticky")
    dev = None
    with devicekit_sdk.db.session() as s:
        row = s.execute(select(sticky).where(sticky.c.token == token)).mappings().first()
        if row:
            dev = row["device_id"]
        s.execute(delete(sticky).where(sticky.c.token == token))
    if dev:
        sessions.set_busy(dev, False)
    return {"released": bool(dev), "device_id": dev}
