"""Notification webhook channel (plan 06.2): secret encryption, channel config masking +
round-trip, severity gating, producer → pending delivery + enqueued job, and the queue-driven
consumer delivering (success → sent) / failing (raise → retry → failed).

The job consumer is driven synchronously (``process_message``) — no daemon threads, the same
seam ``test_jobs`` uses.
"""
import pytest

from devicekit.notifications import catalog, crypto
from devicekit.notifications.service import NotificationService
from devicekit.notifications.config import NotificationChannelService, severity_ok
from devicekit.notifications.consumer import deliver, DELIVER_JOB_KIND
from devicekit.notifications.channels import webhook
from devicekit.models.notification import NotificationDelivery
from devicekit.jobs import registry
from devicekit.jobs.service import JobService, GROUP_SLUG, QUEUE_SLUG, QUEUE_CONFIG
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


def _drain(consumer, max_messages=10):
    msgs = QueueBusService.receive(
        GROUP_SLUG, QUEUE_SLUG,
        visibility_timeout_ms=QUEUE_CONFIG["visibility_timeout_ms"], max_messages=max_messages)
    for m in msgs:
        consumer.process_message(m)
    return len(msgs)


# --------------------------------------------------------------------------- crypto
def test_crypto_round_trip():
    token = crypto.encrypt("https://hooks.slack.com/services/SECRET")
    assert token.startswith("enc:")
    assert crypto.decrypt(token) == "https://hooks.slack.com/services/SECRET"


def test_crypto_passthrough_plaintext():
    assert crypto.decrypt("not-encrypted") == "not-encrypted"
    assert crypto.encrypt("") == ""


# --------------------------------------------------------------------------- config
def test_channel_config_masks_secret_and_round_trips(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={
        "url": "https://hooks.slack.com/services/T/B/XYZ", "format": "slack"})
    masked = NotificationChannelService.get_masked("webhook")
    assert masked["enabled"] is True
    assert masked["config"]["url"] == "••••••"           # never leaked
    # In-process decrypted view has the real value.
    real = NotificationChannelService.get("webhook")
    assert real["config"]["url"].endswith("/XYZ")


def test_channel_config_mask_resubmit_keeps_secret(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x/y"})
    # UI re-saves with the mask sentinel + a format change — secret must be preserved.
    NotificationChannelService.set("webhook", config={"url": "••••••", "format": "discord"})
    real = NotificationChannelService.get("webhook")
    assert real["config"]["url"] == "https://x/y"
    assert real["config"]["format"] == "discord"


def test_severity_gating():
    assert severity_ok("info", "warning") is True
    assert severity_ok("warning", "info") is False
    assert severity_ok("critical", "critical") is True


# --------------------------------------------------------------------------- render
def test_webhook_render_slack_and_discord():
    n = {"title": "Down", "body": "no hb", "severity": "critical", "category": "device",
         "event_key": "device.offline"}
    slack = webhook.render(n, "slack")
    assert "Down" in slack["text"] and slack["attachments"][0]["color"] == "#ef4444"
    discord = webhook.render(n, "discord")
    assert discord["embeds"][0]["title"] == "Down"


# --------------------------------------------------------------------------- produce → deliver
def test_send_plans_pending_delivery_and_enqueues_job(fresh_db, monkeypatch):
    NotificationChannelService.set("webhook", enabled=True, config={
        "url": "https://hooks.example/abc", "format": "slack", "min_severity": "info"})

    posted = {}

    def _post(url, **kw):
        posted["url"] = url
        posted["json"] = kw.get("json")
        return _FakeResp()
    monkeypatch.setattr(webhook.requests, "post", _post)

    n = NotificationService.send("device.offline", data={"device_id": "d", "device_name": "P"})
    deliveries = NotificationService.list_deliveries(n["id"])
    inapp = [d for d in deliveries if d["channel"] == "inapp"]
    hook = [d for d in deliveries if d["channel"] == "webhook"]
    assert len(inapp) == 1 and inapp[0]["status"] == "sent"
    assert len(hook) == 1 and hook[0]["status"] == "pending"
    assert hook[0]["job_id"]
    # The persisted target is a non-secret hint, not the full URL.
    assert "abc" not in hook[0]["target"]

    # Drain the delivery job → webhook transmitted, delivery flips to sent.
    consumer = JobConsumer()
    assert _drain(consumer) == 1
    assert posted["url"] == "https://hooks.example/abc"
    hook = [d for d in NotificationService.list_deliveries(n["id"]) if d["channel"] == "webhook"]
    assert hook[0]["status"] == "sent" and hook[0]["attempts"] == 1


def test_disabled_channel_plans_no_webhook_delivery(fresh_db):
    NotificationChannelService.set("webhook", enabled=False, config={"url": "https://x"})
    n = NotificationService.send("device.offline", data={"device_id": "d"})
    channels = {d["channel"] for d in NotificationService.list_deliveries(n["id"])}
    assert channels == {"inapp"}


def test_severity_below_threshold_is_not_delivered(fresh_db):
    NotificationChannelService.set("webhook", enabled=True, config={
        "url": "https://x", "min_severity": "critical"})
    n = NotificationService.send("device.online", data={"device_id": "d"})  # info
    channels = {d["channel"] for d in NotificationService.list_deliveries(n["id"])}
    assert "webhook" not in channels


def test_delivery_failure_retries_then_marks_failed(fresh_db, monkeypatch):
    NotificationChannelService.set("webhook", enabled=True, config={"url": "https://x"})

    def boom(url, **kw):
        return _FakeResp(status_code=500, text="server error")
    monkeypatch.setattr(webhook.requests, "post", boom)

    n = NotificationService.send("automation.run.failed",
                                 data={"automation_name": "x", "step_index": 0, "error": "e"})
    hook = [d for d in NotificationService.list_deliveries(n["id"]) if d["channel"] == "webhook"][0]

    # Enqueued with max_attempts=4; drive redeliveries until the queue dead-letters.
    consumer = JobConsumer()
    for _ in range(6):
        if _drain(consumer) == 0:
            # Backoff makes the message temporarily invisible; force-reap and retry.
            QueueBusService.reap_expired(GROUP_SLUG, QUEUE_SLUG)
    final = NotificationService.get_delivery(hook["id"])
    assert final["status"] == "failed"
    assert final["attempts"] >= 1
    assert "500" in final["error"]


def test_transmit_raises_on_non_2xx(fresh_db, monkeypatch):
    monkeypatch.setattr(webhook.requests, "post",
                        lambda url, **kw: _FakeResp(status_code=404, text="nope"))
    with pytest.raises(RuntimeError):
        webhook.transmit("https://x", {"text": "hi"})
