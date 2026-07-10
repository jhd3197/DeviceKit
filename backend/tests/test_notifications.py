"""Notification bus (plan 06): catalog rendering, producer + in-app delivery over SSE,
read/unread, mark-read, delete/clear, prune, and restart durability.

The service layer is host-independent (plain ``session_scope``), so these drive it directly
and capture the SSE emit callback — no Flask app, no daemon threads.
"""
import pytest

from devicekit.notifications import catalog
from devicekit.notifications.service import NotificationService
from devicekit.models.notification import NotificationDelivery


@pytest.fixture(autouse=True)
def _seed_catalog():
    catalog.clear()
    catalog.seed_default_events()
    yield
    catalog.clear()


def _emitter():
    seen = []
    return seen, (lambda event_type, data: seen.append((event_type, data)))


# --------------------------------------------------------------------------- catalog
def test_catalog_renders_title_body_and_deep_link():
    entry = catalog.get("device.offline")
    data = {"device_id": "abc", "device_name": "Pixel 7"}
    assert entry.render_title(data) == "Pixel 7 went offline"
    assert entry.render_deep_link(data) == "/devices/abc"
    assert "abc" in entry.render_body(data)


def test_catalog_missing_key_renders_empty_not_crash():
    entry = catalog.get("device.battery.critical")
    # No 'level' provided — must not raise, just render empty for the missing field.
    title = entry.render_title({"device_name": "X"})
    assert "X battery critical" in title


def test_catalog_unknown_event_uses_fallback():
    entry = catalog.get("totally.unknown.event")
    assert entry.render_title({}) == "totally.unknown.event"
    assert entry.severity == "info"


def test_catalog_register_is_used_by_send(fresh_db):
    catalog.register("ext.custom", "Custom {thing}", severity="critical", category="ext",
                     deep_link="/x/{thing}")
    n = NotificationService.send("ext.custom", data={"thing": "widget"})
    assert n["title"] == "Custom widget"
    assert n["severity"] == "critical"
    assert n["deep_link"] == "/x/widget"


# --------------------------------------------------------------------------- produce
def test_send_persists_notification_and_inapp_delivery_and_emits(fresh_db):
    seen, emit = _emitter()
    n = NotificationService.send(
        "device.offline", data={"device_id": "d1", "device_name": "Pixel"},
        subject_type="device", subject_id="d1", emit=emit)

    assert n["title"] == "Pixel went offline"
    assert n["read"] is False
    assert n["subject_id"] == "d1"

    # In-app delivery recorded as sent.
    deliveries = NotificationService.list_deliveries(n["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["channel"] == NotificationDelivery.STATUS_SENT or \
        deliveries[0]["status"] == "sent"
    assert deliveries[0]["channel"] == "inapp"

    # SSE emit fired with the rendered payload.
    assert ("notification", n) in [(et, d) for et, d in seen] or \
        any(et == "notification" and d["id"] == n["id"] for et, d in seen)


def test_send_never_raises_without_emit(fresh_db):
    n = NotificationService.send("device.online", data={"device_id": "d2"})
    assert n["id"]
    assert NotificationService.unread_count() == 1


# --------------------------------------------------------------------------- read/query
def test_list_count_and_unread(fresh_db):
    NotificationService.send("device.offline", data={"device_id": "a"})
    NotificationService.send("device.offline", data={"device_id": "b"})
    assert NotificationService.count() == 2
    assert NotificationService.unread_count() == 2
    items = NotificationService.list()
    assert len(items) == 2
    # Newest first.
    assert items[0]["created_at"] >= items[1]["created_at"]


def test_severity_and_unread_filters(fresh_db):
    NotificationService.send("device.online", data={"device_id": "a"})          # info
    crit = NotificationService.send("automation.run.failed",
                                    data={"automation_name": "x", "step_index": 0})  # critical
    NotificationService.mark_read(crit["id"])
    assert len(NotificationService.list(severity="critical")) == 1
    assert len(NotificationService.list(unread_only=True)) == 1


def test_mark_read_and_mark_all_read(fresh_db):
    a = NotificationService.send("device.offline", data={"device_id": "a"})
    NotificationService.send("device.offline", data={"device_id": "b"})
    updated = NotificationService.mark_read(a["id"])
    assert updated["read"] is True and updated["read_at"]
    assert NotificationService.unread_count() == 1
    assert NotificationService.mark_all_read() == 1
    assert NotificationService.unread_count() == 0


def test_mark_read_missing_returns_none(fresh_db):
    assert NotificationService.mark_read("nope") is None


def test_delete_and_clear(fresh_db):
    a = NotificationService.send("device.offline", data={"device_id": "a"})
    NotificationService.send("device.offline", data={"device_id": "b"})
    assert NotificationService.delete(a["id"]) is True
    assert NotificationService.get(a["id"]) is None
    # Its delivery rows are gone too.
    assert NotificationService.list_deliveries(a["id"]) == []
    assert NotificationService.clear_all() == 1
    assert NotificationService.count() == 0


def test_recipient_scoping(fresh_db):
    NotificationService.send("device.offline", data={"device_id": "a"}, recipient="alice")
    NotificationService.send("device.offline", data={"device_id": "b"}, recipient="bob")
    assert NotificationService.count(recipient="alice") == 1
    assert NotificationService.unread_count(recipient="bob") == 1
    assert NotificationService.count(recipient="default") == 0


# --------------------------------------------------------------------------- prune
def test_prune_keeps_unread_and_recent(fresh_db):
    import time
    from devicekit.db import session_scope
    from devicekit.models.notification import Notification

    old_read = NotificationService.send("device.offline", data={"device_id": "a"})
    old_unread = NotificationService.send("device.offline", data={"device_id": "b"})
    NotificationService.mark_read(old_read["id"])
    # Age both notifications well past retention.
    with session_scope() as s:
        for nid in (old_read["id"], old_unread["id"]):
            s.get(Notification, nid).created_at = time.time() - 100 * 86400

    pruned = NotificationService.prune(retention_days=30, keep_unread=True)
    assert pruned == 1                       # only the old *read* one
    assert NotificationService.get(old_read["id"]) is None
    assert NotificationService.get(old_unread["id"]) is not None


# --------------------------------------------------------------------------- durability
def test_notifications_survive_restart(fresh_db, restart):
    NotificationService.send("device.offline", data={"device_id": "a", "device_name": "P"})
    restart(fresh_db)
    items = NotificationService.list()
    assert len(items) == 1
    assert items[0]["title"] == "P went offline"
    assert NotificationService.unread_count() == 1
