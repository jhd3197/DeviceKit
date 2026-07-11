"""Blueprint for devicekit-browser (mounted at ``/ext/devicekit-browser``).

Device-scoped routes follow the convention ``/ext/<slug>/devices/<device_id>/<verb>`` — the
same ``device_id`` addressing as core routes. Pool routes treat many devices as one browser
farm. The host attaches a status guard so every route 503s when the extension is disabled.
"""
from flask import Blueprint, jsonify, request, Response

import devicekit_sdk

from . import cdp, sessions, pools
from .cdp import CDPError
from .pools import PoolError

SLUG = "devicekit-browser"
bp = Blueprint("devicekit_browser", __name__)
log = devicekit_sdk.logger(SLUG)


def _err(message, code):
    return jsonify({"error": message}), code


@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "extension": SLUG, "sessions": len(sessions.list_sessions())})


# --------------------------------------------------------------------------- device API
@bp.route("/devices/<device_id>/session", methods=["POST"])
def open_session(device_id):
    try:
        return jsonify(sessions.ensure_session(device_id))
    except CDPError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/session", methods=["DELETE"])
def delete_session(device_id):
    return jsonify(sessions.close_session(device_id))


@bp.route("/devices/<device_id>/goto", methods=["POST"])
def goto(device_id):
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return _err("url is required", 400)
    try:
        port, tid = sessions.session_context(device_id)
        final = cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())
        return jsonify({"device_id": device_id, "url": final})
    except CDPError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/content", methods=["GET"])
def get_content(device_id):
    fmt = request.args.get("format", "html")
    try:
        port, tid = sessions.session_context(device_id)
        value = cdp.content(port, tid, fmt=fmt, timeout=sessions.cdp_timeout())
        return jsonify({"device_id": device_id, "format": fmt, "content": value})
    except CDPError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/evaluate", methods=["POST"])
def evaluate(device_id):
    data = request.get_json(silent=True) or {}
    expression = data.get("expression")
    if not expression:
        return _err("expression is required", 400)
    try:
        port, tid = sessions.session_context(device_id)
        value = cdp.evaluate(port, tid, expression, timeout=sessions.cdp_timeout())
        return jsonify({"device_id": device_id, "value": value})
    except CDPError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/screenshot", methods=["GET"])
def screenshot(device_id):
    full = request.args.get("full", "").lower() in ("1", "true", "yes")
    try:
        port, tid = sessions.session_context(device_id)
        png = cdp.screenshot(port, tid, full_page=full, timeout=sessions.cdp_timeout())
        return Response(png, mimetype="image/png")
    except CDPError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/tabs", methods=["GET"])
def tabs(device_id):
    try:
        port, _tid = sessions.session_context(device_id)
        return jsonify({"device_id": device_id, "tabs": cdp.tabs(port)})
    except CDPError as e:
        return _err(str(e), 502)


# --------------------------------------------------------------------------- pool API
@bp.route("/pools", methods=["GET"])
def list_pools():
    items = pools.list_pools()
    return jsonify({"pools": items, "count": len(items)})


@bp.route("/pools", methods=["POST"])
def create_pool():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    strategy = data.get("strategy", "round_robin")
    spec = {k: data[k] for k in ("devices", "fql", "all") if k in data}
    try:
        return jsonify(pools.create_pool(name, spec, strategy)), 201
    except PoolError as e:
        return _err(str(e), 400)


@bp.route("/pools/<name>", methods=["DELETE"])
def delete_pool(name):
    if not pools.get_pool(name):
        return _err(f"pool '{name}' not found", 404)
    return jsonify(pools.delete_pool(name))


@bp.route("/pools/<name>/status", methods=["GET"])
def pool_status(name):
    pool = pools.get_pool(name)
    if not pool:
        return _err(f"pool '{name}' not found", 404)
    try:
        return jsonify(pools.pool_status(pool))
    except PoolError as e:
        return _err(str(e), 400)


def _dispatch(pool, work):
    """Try devices from the pool with transparent failover; ``work(device_id)`` runs against a
    picked device and returns a result. On CDPError the device is cooled down and the next is
    tried. Returns (device_id, result)."""
    excluded = set()
    members = pools.resolve_members(pool)
    last_err = None
    for _ in range(max(1, len(members))):
        device_id = pools.pick_device(pool, exclude=excluded)
        try:
            return device_id, work(device_id)
        except CDPError as e:
            last_err = e
            pools.mark_unhealthy(device_id)
            excluded.add(device_id)
            log.warning(f"pool '{pool['name']}' device {device_id} failed: {e}; failing over")
    raise CDPError(str(last_err) if last_err else "no device could serve the request")


@bp.route("/pools/<name>/fetch", methods=["POST"])
def pool_fetch(name):
    pool = pools.get_pool(name)
    if not pool:
        return _err(f"pool '{name}' not found", 404)
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return _err("url is required", 400)
    fmt = data.get("format", "html")
    want_shot = bool(data.get("screenshot"))

    def work(device_id):
        port, tid = sessions.session_context(device_id)
        cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())
        out = {}
        if want_shot:
            import base64
            out["screenshot"] = base64.b64encode(
                cdp.screenshot(port, tid, timeout=sessions.cdp_timeout())).decode("ascii")
        else:
            out[fmt if fmt in ("html", "text", "title") else "content"] = cdp.content(
                port, tid, fmt=fmt, timeout=sessions.cdp_timeout())
        return out

    try:
        device_id, result = _dispatch(pool, work)
        return jsonify({"device_id": device_id, "url": url, **result})
    except (CDPError, PoolError) as e:
        return _err(str(e), 502)


@bp.route("/pools/<name>/goto", methods=["POST"])
def pool_goto(name):
    """Like fetch, but leaves the session open and returns a sticky ``session_token`` that pins
    subsequent calls to the served device until released/timed out."""
    pool = pools.get_pool(name)
    if not pool:
        return _err(f"pool '{name}' not found", 404)
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return _err("url is required", 400)

    def work(device_id):
        port, tid = sessions.session_context(device_id)
        return cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())

    try:
        device_id, final = _dispatch(pool, work)
    except (CDPError, PoolError) as e:
        return _err(str(e), 502)
    sessions.set_busy(device_id, True)   # pin: round-robin skips it while the flow runs
    token = pools.create_sticky(device_id, name, ttl=int(data.get("ttl") or pools.DEFAULT_STICKY_TTL))
    return jsonify({"device_id": device_id, "url": final, "session_token": token})


@bp.route("/sessions/<token>/release", methods=["POST"])
def release_session(token):
    info = pools.resolve_sticky(token)
    result = pools.release_sticky(token)
    if not info and not result.get("released"):
        return _err("unknown or expired session_token", 404)
    return jsonify(result)
