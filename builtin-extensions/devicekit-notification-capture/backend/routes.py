"""Blueprint for devicekit-notification-capture (mounted at
``/ext/devicekit-notification-capture``). Read the captured feed and trigger an immediate poll.
"""
from flask import Blueprint, jsonify, request

import devicekit_sdk

from . import capture

SLUG = "devicekit-notification-capture"
bp = Blueprint("devicekit_notification_capture", __name__)
log = devicekit_sdk.logger(SLUG)


@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "extension": SLUG, "capable_devices": capture.capable_devices()})


@bp.route("/notifications", methods=["GET"])
def list_notifications():
    device_id = request.args.get("device_id") or None
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (TypeError, ValueError):
        limit = 50
    items = capture.recent(device_id=device_id, limit=limit)
    return jsonify({"notifications": items, "count": len(items)})


@bp.route("/devices/<device_id>/notifications", methods=["GET"])
def device_notifications(device_id):
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (TypeError, ValueError):
        limit = 50
    items = capture.recent(device_id=device_id, limit=limit)
    return jsonify({"device_id": device_id, "notifications": items, "count": len(items)})


@bp.route("/poll", methods=["POST"])
def poll_now():
    """Trigger an immediate capture pass (in addition to the scheduled poll)."""
    result = capture.poll({})
    return jsonify(result)
