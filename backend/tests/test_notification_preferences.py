"""Notification preferences (plan 06.3): per-event + per-channel mutes, quiet hours,
digest batching, and the email channel.

Async delivery is driven synchronously via the job consumer where relevant; the email SMTP
client and webhook HTTP client are monkeypatched.
"""
from datetime import datetime

import pytest

from devicekit.notifications import catalog
from devicekit.notifications.service import NotificationService
from devicekit.notifications.config import NotificationChannelService
from devicekit.notifications.preferences import (
    PreferenceService, flush_digests, DIGEST_CHANNEL, _hour_in_window)
from devicekit.notifications.consumer import deliver, DELIVER_JOB_KIND
from devicekit.notifications.channels import webhook, email
from devicekit.jobs import registry
from devicekit.jobs.service import GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
from devicekit.jobs.consumer import JobConsumer
from devicekit.queue_bus.service import QueueBusService


@pytest.fixture(autouse=True)
def _seed_and_clean():
    catalog.clear()
    catalog.seed_default_events()
    registry.clear()
    registry.register(DELIVER_JOB_KIND, deliver)
    yield
    registry.clear()
    catalog.clear()


class _FakeResp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def _channels(notif_id, chan=None):
    ds = NotificationService.list_deliveries(notif_id)
    return [d for d in ds if chan is None or d["channel"] == chan]


# --------------------------------------------------------------------------- mutes
def test_full_mute_drops_notification(fresh_db):
    PreferenceService.set_pref("default", "device.offline")   # channel=None → full mute
    n = NotificationService.send("device.offline", data={"device_id": "a"})
    assert n is None
    assert NotificationService.count() == 0


def test_inapp_channel_mute_keeps_history_no_delivery(fresh_db):
    PreferenceService.set_pref("default", "device.offline", channel="inapp")
    n = NotificationService.send("device.offline", data={"device_id": "a"})
    assert n is not None                       # history row still created
    assert _channels(n["id"], "inapp") == []   # but no in-app delivery


def test_webhook_channel_mute_skips_webhook(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x"})
    PreferenceService.set_pref("default", "device.offline", channel="webhook")
    n = NotificationService.send("device.offline", data={"device_id": "a"})
    assert _channels(n["id"], "webhook") == []
    assert len(_channels(n["id"], "inapp")) == 1


def test_unmute_deletes_rule(fresh_db):
    PreferenceService.set_pref("default", "device.offline")
    assert PreferenceService.is_event_muted("default", "device.offline") is True
    PreferenceService.set_pref("default", "device.offline", muted=False)
    assert PreferenceService.is_event_muted("default", "device.offline") is False


# --------------------------------------------------------------------------- quiet hours
def test_hour_window_wraps_midnight():
    assert _hour_in_window(23, 22, 7) is True
    assert _hour_in_window(3, 22, 7) is True
    assert _hour_in_window(12, 22, 7) is False
    assert _hour_in_window(9, 8, 17) is True


def test_quiet_allows_only_critical_breakthrough(fresh_db):
    now = datetime(2026, 7, 10, 23, 0, 0)   # inside a 22–7 window
    PreferenceService.set_settings(
        "default", quiet_hours_enabled=True, quiet_start=22, quiet_end=7,
        quiet_allow_critical=True)
    assert PreferenceService.quiet_allows("default", "warning", now=now) is False
    assert PreferenceService.quiet_allows("default", "critical", now=now) is True


def test_quiet_hours_suppress_async_but_keep_inapp(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x"})
    # Make quiet hours cover the current hour (span of 2h to avoid an end-of-hour flake).
    h = datetime.now().hour
    PreferenceService.set_settings(
        "default", quiet_hours_enabled=True, quiet_start=h, quiet_end=(h + 2) % 24,
        quiet_allow_critical=True)

    warn = NotificationService.send("device.storage.low",
                                    data={"device_id": "a", "free_pct": 3})  # warning
    assert _channels(warn["id"], "webhook") == []          # async suppressed
    assert len(_channels(warn["id"], "inapp")) == 1        # in-app kept

    crit = NotificationService.send("device.battery.critical",
                                    data={"device_id": "a", "level": 4})     # critical
    assert len(_channels(crit["id"], "webhook")) == 1      # critical breaks through


# --------------------------------------------------------------------------- digest
def test_digest_batches_then_flush_delivers(fresh_db, monkeypatch):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x"})
    PreferenceService.set_settings(
        "default", digest_enabled=True, digest_events=["device.offline"])

    posted = []
    monkeypatch.setattr(webhook.requests, "post",
                        lambda url, **kw: posted.append(kw.get("json")) or _FakeResp())

    a = NotificationService.send("device.offline", data={"device_id": "a", "device_name": "A"})
    b = NotificationService.send("device.offline", data={"device_id": "b", "device_name": "B"})
    # No immediate webhook delivery — just a pending digest marker each.
    assert _channels(a["id"], "webhook") == []
    assert len(_channels(a["id"], DIGEST_CHANNEL)) == 1
    assert len(_channels(b["id"], DIGEST_CHANNEL)) == 1

    result = flush_digests()
    assert result["notifications"] == 2
    assert len(posted) == 1                                # one batched webhook
    assert "2 notification" in posted[0]["text"]
    # Markers are now sent, so a second flush is a no-op.
    assert flush_digests()["notifications"] == 0


def test_non_digest_event_delivers_immediately(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x"})
    PreferenceService.set_settings(
        "default", digest_enabled=True, digest_events=["device.offline"])
    # A different event is not digested → normal pending webhook delivery.
    n = NotificationService.send("automation.run.failed",
                                 data={"automation_name": "x", "step_index": 0})
    assert len(_channels(n["id"], "webhook")) == 1


# --------------------------------------------------------------------------- email
def test_email_build_message():
    msg = email.build_message(
        {"title": "Down", "body": "no hb", "severity": "critical", "deep_link": "/devices/x"},
        {"from_addr": "a@x.com", "to_addrs": "b@x.com, c@x.com"})
    assert "CRITICAL" in msg["Subject"] and "Down" in msg["Subject"]
    assert msg["To"] == "b@x.com, c@x.com"
    assert "/devices/x" in msg.get_content()


def test_email_send_via_fake_smtp(fresh_db, monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host; sent["port"] = port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, msg): sent["to"] = msg["To"]

    monkeypatch.setattr(email.smtplib, "SMTP", _FakeSMTP)
    email.send(
        {"title": "Hi", "body": "", "severity": "info"},
        {"smtp_host": "smtp.x", "smtp_port": 587, "smtp_user": "u", "smtp_password": "p",
         "from_addr": "a@x.com", "to_addrs": "b@x.com", "use_tls": True})
    assert sent["host"] == "smtp.x" and sent["tls"] is True
    assert sent["login"] == ("u", "p") and sent["to"] == "b@x.com"


def test_email_delivery_end_to_end_via_consumer(fresh_db, monkeypatch):
    class _FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): _FakeSMTP.sent = True

    monkeypatch.setattr(email.smtplib, "SMTP", _FakeSMTP)
    NotificationChannelService.set("email", enabled=True, config={
        "smtp_host": "smtp.x", "from_addr": "a@x.com", "to_addrs": "b@x.com",
        "min_severity": "info"})

    n = NotificationService.send("device.offline", data={"device_id": "d", "device_name": "D"})
    consumer = JobConsumer()
    msgs = QueueBusService.receive(GROUP_SLUG, QUEUE_SLUG,
                                   visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"],
                                   max_messages=10)
    for m in msgs:
        consumer.process_message(m)
    hook = _channels(n["id"], "email")[0]
    assert hook["status"] == "sent"
    assert getattr(_FakeSMTP, "sent", False) is True
