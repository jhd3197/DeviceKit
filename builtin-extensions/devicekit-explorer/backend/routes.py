"""Blueprint for devicekit-explorer (mounted at ``/ext/devicekit-explorer``).

Fills the file-API gaps the dashboard needs — list, destructive verbs (delete/mkdir/rename),
and a bounded preview — WITHOUT editing host code, as a dogfood test of "can an extension
deliver a complete feature from a blueprint alone". Every verb is gated by the ``filesystem``
permission and proxies to the on-device agent's file server (the same agent HTTP API core's
file routes use); there is no adb shell path, so nothing here can escape the agent's own file
sandbox. Agent-only: a device with no online agent gets a clear 503.
"""
import mimetypes

import requests
from flask import Blueprint, jsonify, request, Response

import devicekit_sdk
from devicekit_sdk import require_permission

SLUG = "devicekit-explorer"
bp = Blueprint("devicekit_explorer", __name__)
log = devicekit_sdk.logger(SLUG)

PREVIEW_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB cap for the UI preview


def _err(message, code):
    return jsonify({"error": message}), code


def _agent_base(device_id):
    """Resolve ``http://<ip>:<port>`` for a device's online agent, or ``None``."""
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
    ip = info.get("ip") or request.remote_addr
    port = info.get("agent_port", 9800)
    return f"http://{ip}:{port}" if ip else None


@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "extension": SLUG})


@bp.route("/devices/<device_id>/files", methods=["GET"])
def list_files(device_id):
    require_permission(SLUG, "filesystem")
    path = request.args.get("path") or "/sdcard"
    base = _agent_base(device_id)
    if not base:
        return _err("Agent not available for this device", 503)
    try:
        r = requests.get(f"{base}/files/list", params={"path": path}, timeout=8)
        if not r.ok:
            return _err(f"list failed ({r.status_code})", 502)
        data = r.json()
    except Exception as e:
        return _err(f"agent list failed: {e}", 502)
    entries = [{
        "name": i.get("name"),
        "is_dir": i.get("is_dir"),
        "size": i.get("size"),
        "mtime": i.get("modified"),
        "path": i.get("path"),
    } for i in data.get("items", [])]
    return jsonify({"path": path, "entries": entries, "count": len(entries), "source": "agent"})


@bp.route("/devices/<device_id>/files", methods=["DELETE"])
def delete_file(device_id):
    require_permission(SLUG, "filesystem")
    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        return _err("path is required", 400)
    base = _agent_base(device_id)
    if not base:
        return _err("Agent not available for this device", 503)
    try:
        r = requests.post(f"{base}/files/delete", json={"path": path}, timeout=15)
        return jsonify(r.json() if r.content else {"success": r.ok}), (200 if r.ok else 502)
    except Exception as e:
        return _err(f"agent delete failed: {e}", 502)


@bp.route("/devices/<device_id>/files/mkdir", methods=["POST"])
def mkdir(device_id):
    require_permission(SLUG, "filesystem")
    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        return _err("path is required", 400)
    base = _agent_base(device_id)
    if not base:
        return _err("Agent not available for this device", 503)
    try:
        r = requests.post(f"{base}/files/mkdir", json={"path": path}, timeout=10)
        return jsonify(r.json() if r.content else {"success": r.ok}), (200 if r.ok else 502)
    except Exception as e:
        return _err(f"agent mkdir failed: {e}", 502)


@bp.route("/devices/<device_id>/files/rename", methods=["POST"])
def rename(device_id):
    require_permission(SLUG, "filesystem")
    data = request.get_json(silent=True) or {}
    src, dst = data.get("from"), data.get("to")
    if not src or not dst:
        return _err("'from' and 'to' are required", 400)
    base = _agent_base(device_id)
    if not base:
        return _err("Agent not available for this device", 503)
    try:
        r = requests.post(f"{base}/files/rename", json={"from": src, "to": dst}, timeout=10)
        return jsonify(r.json() if r.content else {"success": r.ok}), (200 if r.ok else 502)
    except Exception as e:
        return _err(f"agent rename failed: {e}", 502)


@bp.route("/devices/<device_id>/files/preview", methods=["GET"])
def preview(device_id):
    require_permission(SLUG, "filesystem")
    path = request.args.get("path")
    if not path:
        return _err("path is required", 400)
    base = _agent_base(device_id)
    if not base:
        return _err("Agent not available for this device", 503)
    try:
        r = requests.get(f"{base}/files/read", params={"path": path}, stream=True, timeout=20)
        if not r.ok:
            return _err(f"read failed ({r.status_code})", 502)
        buf = bytearray()
        for chunk in r.iter_content(8192):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= PREVIEW_MAX_BYTES:
                break
    except Exception as e:
        return _err(f"preview failed: {e}", 502)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    resp = Response(bytes(buf), mimetype=ctype)
    resp.headers["X-Preview-Truncated"] = "1" if len(buf) >= PREVIEW_MAX_BYTES else "0"
    return resp
