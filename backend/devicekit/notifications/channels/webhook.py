"""Webhook notification channel (plan 06.2).

Posts a notification to a Slack/Discord-compatible incoming webhook. Cheapest high-value
channel for CI labs: a fleet event lands in a team channel with no email plumbing. Delivery
is asynchronous — the ``NotificationConsumer`` calls :func:`render` + :func:`transmit` from a
queue-driven job so a slow/failing endpoint retries via the Queue Bus instead of blocking the
producer.

``format`` selects the payload shape:

* ``slack``  → ``{"text": "...", "attachments": [{"color", "title", "text"}]}``
* ``discord`` → ``{"content": "...", "embeds": [{"title", "description", "color"}]}``
* ``generic`` → the raw notification dict (for custom receivers)
"""
import logging

import requests

logger = logging.getLogger(__name__)

CHANNEL = "webhook"
TIMEOUT_SECONDS = 10

# Severity → accent color (Slack hex string / Discord int).
_SLACK_COLOR = {"info": "#3b82f6", "warning": "#f59e0b", "critical": "#ef4444"}
_DISCORD_COLOR = {"info": 0x3B82F6, "warning": 0xF59E0B, "critical": 0xEF4444}


def render(notif, fmt="slack"):
    """Build the webhook JSON body for ``notif`` in the requested format."""
    title = notif.get("title", "")
    body = notif.get("body", "") or ""
    severity = notif.get("severity", "info")
    text = f"*{title}*"
    if body:
        text += f"\n{body}"

    if fmt == "discord":
        return {
            "content": title,
            "embeds": [{
                "title": title,
                "description": body or None,
                "color": _DISCORD_COLOR.get(severity, _DISCORD_COLOR["info"]),
            }],
        }
    if fmt == "generic":
        return {"notification": notif}
    # Default: Slack incoming-webhook shape.
    return {
        "text": text,
        "attachments": [{
            "color": _SLACK_COLOR.get(severity, _SLACK_COLOR["info"]),
            "title": title,
            "text": body,
            "footer": f"DeviceKit · {notif.get('category', 'general')} · {notif.get('event_key', '')}",
        }],
    }


def transmit(url, payload, timeout=TIMEOUT_SECONDS):
    """POST ``payload`` to ``url``. Raises on a network error or non-2xx response so the
    caller (delivery job) fails and the Queue Bus retries."""
    if not url:
        raise ValueError("Webhook URL is not configured")
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code >= 300:
        raise RuntimeError(f"Webhook returned HTTP {resp.status_code}: {resp.text[:200]}")
    return {"status_code": resp.status_code}
