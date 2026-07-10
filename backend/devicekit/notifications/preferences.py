"""Notification preferences: per-event mutes, quiet hours, and digest batching (plan 06.3).

The producer consults this layer to decide *whether* and *through which channels* a
notification is delivered:

* **mute** — a full mute (``channel is None``) drops the event entirely; a per-channel mute
  silences one transport (e.g. keep the in-app entry, mute Slack);
* **quiet hours** — during the daily window, async channels are suppressed (in-app still
  recorded) unless the event is ``critical`` and break-through is on;
* **digest** — listed noisy events are not pushed immediately; a marker delivery is recorded
  and :func:`flush_digests` (a scheduled job) batches them into one summary per recipient.
"""
import logging
import time
from datetime import datetime

from devicekit.db import session_scope
from devicekit.models.notification import (
    Notification, NotificationDelivery, NotificationPreference, NotificationRecipientSettings)

logger = logging.getLogger(__name__)

DIGEST_CHANNEL = "digest"

_DEFAULT_SETTINGS = {
    "quiet_hours_enabled": False,
    "quiet_start": 22,
    "quiet_end": 7,
    "quiet_allow_critical": True,
    "digest_enabled": False,
    "digest_window_minutes": 15,
    "digest_events": [],
}


def _hour_in_window(hour, start, end):
    """True if ``hour`` falls in the [start, end) window, handling wrap past midnight."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps midnight


class PreferenceService:

    # ---------------------------------------------------------------- settings
    @classmethod
    def get_settings(cls, recipient="default"):
        with session_scope() as s:
            row = s.get(NotificationRecipientSettings, recipient)
            if not row:
                data = dict(_DEFAULT_SETTINGS)
                data["recipient"] = recipient
                return data
            return row.to_dict()

    @classmethod
    def set_settings(cls, recipient="default", **fields):
        allowed = set(_DEFAULT_SETTINGS.keys())
        with session_scope() as s:
            row = s.get(NotificationRecipientSettings, recipient)
            if not row:
                row = NotificationRecipientSettings(recipient=recipient)
                s.add(row)
            for k, v in fields.items():
                if k in allowed:
                    setattr(row, k, v)
            row.updated_at = time.time()
            s.flush()
            return row.to_dict()

    # ------------------------------------------------------------------- mutes
    @classmethod
    def list_prefs(cls, recipient="default"):
        with session_scope() as s:
            rows = (s.query(NotificationPreference)
                    .filter(NotificationPreference.recipient == recipient)
                    .filter(NotificationPreference.muted.is_(True)).all())
            return [r.to_dict() for r in rows]

    @classmethod
    def set_pref(cls, recipient, event_key, channel=None, muted=True):
        """Upsert a mute rule. ``muted=False`` deletes the rule (un-mute)."""
        with session_scope() as s:
            row = (s.query(NotificationPreference)
                   .filter_by(recipient=recipient, event_key=event_key, channel=channel)
                   .first())
            if not muted:
                if row:
                    s.delete(row)
                return {"recipient": recipient, "event_key": event_key,
                        "channel": channel, "muted": False}
            if not row:
                row = NotificationPreference(
                    recipient=recipient, event_key=event_key, channel=channel)
                s.add(row)
            row.muted = True
            row.updated_at = time.time()
            s.flush()
            return row.to_dict()

    @classmethod
    def _rules(cls, recipient, event_key):
        with session_scope() as s:
            rows = (s.query(NotificationPreference)
                    .filter_by(recipient=recipient, event_key=event_key)
                    .filter(NotificationPreference.muted.is_(True)).all())
            return [(r.channel, r.muted) for r in rows]

    @classmethod
    def is_event_muted(cls, recipient, event_key):
        """True if the event is fully muted (a ``channel is None`` rule)."""
        return any(channel is None for channel, _ in cls._rules(recipient, event_key))

    @classmethod
    def muted_channels(cls, recipient, event_key):
        """Set of specific channels muted for this event (excludes the full-mute rule)."""
        return {channel for channel, _ in cls._rules(recipient, event_key) if channel}

    # ------------------------------------------------------------- quiet hours
    @classmethod
    def in_quiet_hours(cls, recipient="default", now=None):
        settings = cls.get_settings(recipient)
        if not settings["quiet_hours_enabled"]:
            return False
        hour = (now or datetime.now()).hour
        return _hour_in_window(hour, settings["quiet_start"], settings["quiet_end"])

    @classmethod
    def quiet_allows(cls, recipient, severity, now=None):
        """During quiet hours, only ``critical`` (with break-through on) may deliver async."""
        if not cls.in_quiet_hours(recipient, now=now):
            return True
        settings = cls.get_settings(recipient)
        return bool(settings["quiet_allow_critical"]) and severity == "critical"

    # ----------------------------------------------------------------- digest
    @classmethod
    def is_digested(cls, recipient, event_key):
        settings = cls.get_settings(recipient)
        return bool(settings["digest_enabled"]) and event_key in (settings["digest_events"] or [])


def build_digest_summary(notifs):
    """Synthesize a single summary 'notification' dict from a batch."""
    n = len(notifs)
    rank = {"info": 0, "warning": 1, "critical": 2}
    top = max((x.get("severity", "info") for x in notifs), key=lambda s: rank.get(s, 0))
    lines = [f"• {x.get('title', '')}" for x in notifs[:20]]
    if n > 20:
        lines.append(f"…and {n - 20} more")
    return {
        "id": "digest",
        "event_key": "notification.digest",
        "title": f"DeviceKit digest — {n} notification{'s' if n != 1 else ''}",
        "body": "\n".join(lines),
        "severity": top,
        "category": "digest",
        "deep_link": "/notifications",
        "data": {"count": n},
    }


def flush_digests():
    """Batch every recipient's pending digest markers into one summary per enabled async
    channel. Called by the ``notification.digest.flush`` scheduled job. Returns a small
    summary dict. Transmits synchronously (inside the job) — a channel error marks that
    channel's delivery failed but does not block the other channels or recipients."""
    from devicekit.notifications.config import NotificationChannelService, severity_ok
    from devicekit.notifications.service import NotificationService, _target_hint
    from devicekit.notifications.channels import webhook, email as email_channel

    flushed = {"recipients": 0, "notifications": 0, "deliveries": 0}

    # Which recipients have digesting on?
    with session_scope() as s:
        recips = [r.recipient for r in s.query(NotificationRecipientSettings)
                  .filter(NotificationRecipientSettings.digest_enabled.is_(True)).all()]

    for recipient in recips:
        settings = PreferenceService.get_settings(recipient)
        events = settings.get("digest_events") or []
        if not events:
            continue

        # Pending digest markers for this recipient's digested events.
        with session_scope() as s:
            pairs = (s.query(NotificationDelivery, Notification)
                     .join(Notification, NotificationDelivery.notification_id == Notification.id)
                     .filter(NotificationDelivery.channel == DIGEST_CHANNEL)
                     .filter(NotificationDelivery.status == NotificationDelivery.STATUS_PENDING)
                     .filter(Notification.recipient == recipient)
                     .filter(Notification.event_key.in_(events)).all())
            notifs = [n.to_dict() for _, n in pairs]
            marker_ids = [d.id for d, _ in pairs]
        if not notifs:
            continue

        summary = build_digest_summary(notifs)
        for ch in NotificationChannelService.enabled_channels():
            channel, config = ch["channel"], ch["config"]
            if not severity_ok(config.get("min_severity"), summary["severity"]):
                continue
            target = config.get("url") or config.get("to_addrs") or ""
            delivery = NotificationService.record_delivery(
                notifs[0]["id"], channel, NotificationDelivery.STATUS_PENDING,
                target=_target_hint(target))
            try:
                if channel == webhook.CHANNEL:
                    webhook.transmit(config.get("url"),
                                     webhook.render(summary, fmt=config.get("format", "slack")))
                elif channel == email_channel.CHANNEL:
                    email_channel.send(summary, config)
                NotificationService.mark_delivery(
                    delivery["id"], status=NotificationDelivery.STATUS_SENT,
                    sent_at=time.time(), inc_attempts=True)
                flushed["deliveries"] += 1
            except Exception as e:
                logger.warning("Digest delivery via %s failed: %s", channel, e)
                NotificationService.mark_delivery(
                    delivery["id"], status=NotificationDelivery.STATUS_FAILED,
                    error=str(e)[:500], inc_attempts=True)

        # Mark the markers sent so they are not re-flushed.
        for mid in marker_ids:
            NotificationService.mark_delivery(
                mid, status=NotificationDelivery.STATUS_SENT, sent_at=time.time())
        flushed["recipients"] += 1
        flushed["notifications"] += len(notifs)

    return flushed
