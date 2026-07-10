"""Automation step type: ``notify.webhook``.

Because DeviceKit auto-renders the AutomationEditor config form from the step registry, this
step gets full editor UI with zero frontend code — the payoff of the step-type dispatch
registry (plan 03).
"""
from . import notify


def _execute(client, config, device_id):
    message = config.get("message") or ""
    if not message:
        raise ValueError("message is required")
    url = config.get("webhook_url") or None
    record = notify.send(message, url=url)
    if record["error"]:
        raise Exception(f"Webhook delivery failed: {record['error']}")
    return f"Notified webhook (status {record['status_code']})"


def register():
    return {
        "notify.webhook": {
            "label": "Send Webhook Notification",
            "category": "Notify",
            "config": {
                "message": {"type": "text", "label": "Message", "required": True},
                "webhook_url": {"type": "text", "label": "Webhook URL (optional override)", "required": False},
            },
            "execute": _execute,
        }
    }
