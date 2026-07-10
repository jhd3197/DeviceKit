"""Blueprint mounted at ``/extensions/devicekit-webhook-notify`` — a health ping and a
test-send endpoint. The host attaches a status guard so every route here returns 503 when
the extension is disabled."""
from flask import Blueprint, jsonify, request

from . import notify

bp = Blueprint("devicekit_webhook_notify", __name__)


@bp.route("/ping")
def ping():
    configured = bool(notify.resolve_webhook_url())
    return jsonify({"ok": True, "configured": configured})


@bp.route("/test", methods=["POST"])
def test_send():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or notify.devicekit_sdk.config(notify.SLUG).get("default_message") or "DeviceKit test notification"
    try:
        record = notify.send(message, url=data.get("webhook_url"))
        code = 200 if not record["error"] else 502
        return jsonify(record), code
    except Exception as e:
        return jsonify({"error": str(e)}), 400
