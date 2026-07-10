"""Webhook delivery helper.

Posts a Slack/Discord-compatible JSON payload (``{"text": ...}``) to a configured webhook.
Every send goes through the SDK permission gate (``network``) and is recorded in the
extension's own ``ext_devicekit_webhook_notify_deliveries`` table.
"""
import json
import time
import uuid
import urllib.request

import devicekit_sdk
from devicekit_sdk import require_permission

SLUG = "devicekit-webhook-notify"
log = devicekit_sdk.logger(SLUG)


def resolve_webhook_url(override=None):
    if override:
        return override
    return devicekit_sdk.config(SLUG).get("webhook_url", "")


def send(text, url=None):
    """Send ``text`` to the webhook. Returns a delivery record dict; records it to the
    extension's deliveries table."""
    require_permission(SLUG, "network")  # declared in the manifest
    webhook_url = resolve_webhook_url(url)
    if not webhook_url:
        raise ValueError("No webhook_url configured (set it in extension config)")

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "DeviceKit-Webhook"},
        method="POST",
    )
    status = 0
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — user-configured
            status = resp.status
    except Exception as e:  # delivery failures are recorded, not raised past the caller here
        error = str(e)
        log.warning(f"Webhook delivery failed: {e}")

    record = {
        "id": str(uuid.uuid4()),
        "text": text[:500],
        "status_code": status,
        "error": error,
        "sent_at": time.time(),
    }
    _record_delivery(record)
    devicekit_sdk.broadcast("extension_event", {"slug": SLUG, "kind": "webhook_sent", **record})
    return record


def _record_delivery(record):
    from .models import deliveries_table
    try:
        with devicekit_sdk.db.session() as s:
            s.execute(deliveries_table().insert().values(**record))
    except Exception as e:
        log.warning(f"Could not record delivery: {e}")
