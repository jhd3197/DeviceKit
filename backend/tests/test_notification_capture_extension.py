"""devicekit-notification-capture (plan 15 phase 4): the first real external user of the
plan-05 jobs/schedules seam and plan-06 bus. Installing it registers a poll job + schedule,
an ext table, the wait_for_notification step, gated-free read AI tools, a catalog event, and
the OTP automation template. Poll dedup, OTP extraction, and bus forwarding are exercised with
a stubbed agent feed (no phone needed); live capture is verified against a device separately.
"""
import os
import shutil

import pytest
from flask import Flask

from devicekit.mixins.extensions import ExtensionsMixin, _EXTENSIONS_PKG_DIR
from devicekit.mixins.automation import AutomationMixin
from devicekit.mixins.fleet_query import FleetQueryMixin
from devicekit.mixins.jobs import JobsMixin
from devicekit.mixins.notifications import NotificationsMixin
from devicekit.mixins.prompture_agent import build_device_tools

SLUG = "devicekit-notification-capture"
PKG = SLUG.replace("-", "_")


class _ExtClient(ExtensionsMixin, AutomationMixin, FleetQueryMixin, JobsMixin, NotificationsMixin):
    def __init__(self):
        self._agent_device_states = {}
        self.notify_calls = []

    def broadcast(self, *a, **k):
        pass

    def notify_event(self, event_key, **kwargs):
        self.notify_calls.append((event_key, kwargs))
        return super().notify_event(event_key, **kwargs)


@pytest.fixture(autouse=True)
def _clean():
    from devicekit.jobs import registry
    before = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    yield
    after = set(os.listdir(_EXTENSIONS_PKG_DIR)) if os.path.isdir(_EXTENSIONS_PKG_DIR) else set()
    for name in after - before:
        if name != "__init__.py":
            shutil.rmtree(os.path.join(_EXTENSIONS_PKG_DIR, name), ignore_errors=True)
    AutomationMixin._ext_step_types.clear()
    registry.clear()


def _client(with_capable_device=False):
    c = _ExtClient()
    if with_capable_device:
        c._agent_device_states = {
            "dev-1": {"device_id": "dev-1", "online": True,
                      "capabilities": ["notification_listener"],  # list form (the real shape)
                      "info": {"ip": "127.0.0.1", "agent_port": 9800}},
        }
    c.init_extensions()
    c._flask_app = Flask(__name__)
    return c


def _capmod():
    from devicekit.extensions.devicekit_notification_capture import capture
    return capture


def test_capture_installs_and_contributes(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine
    from devicekit.notifications import catalog

    client = _client()
    ext = client.install_builtin_extension(SLUG)
    assert ext["status"] == "active" and ext["source"] == "builtin"

    # Blueprint + step type + AI tools + table.
    assert client._flask_app.test_client().get(f"/ext/{SLUG}/ping").status_code == 200
    assert "wait_for_notification" in client.get_step_types()
    tools = build_device_tools(client, "dev-1")._tools
    assert f"{PKG}__recent_notifications" in tools and f"{PKG}__wait_for_notification" in tools
    assert f"ext_{PKG}_events" in inspect(get_engine()).get_table_names()

    # Job kind + owned schedule (plan 05 seam).
    scheds = client.list_scheduled_jobs(owner_type="extension", owner_id=SLUG)
    assert any(s["kind"] == "devicekit_notification_capture.poll" for s in scheds)

    # Catalog event registered (plan 06 seam).
    assert catalog.get("notification.captured").title == "{package}: {title}"

    # OTP automation template seeded with the {{otp}} wiring.
    seeded = [a for a in client.list_automations() if f"ext:{SLUG}" in (a.get("tags") or [])]
    assert len(seeded) == 1
    types = [s["type"] for s in seeded[0]["steps"]]
    assert "wait_for_notification" in types
    assert any("{{otp}}" in (s.get("config", {}).get("text", "")) for s in seeded[0]["steps"])


def test_capture_poll_dedups(fresh_db, monkeypatch):
    client = _client(with_capable_device=True)
    client.install_builtin_extension(SLUG)
    cap = _capmod()
    feed = [
        {"package": "com.sms", "title": "Bank", "text": "code 111111", "timestamp": 1000},
        {"package": "com.sms", "title": "Bank", "text": "code 222222", "timestamp": 2000},
    ]
    monkeypatch.setattr(cap, "fetch_notifications", lambda did: feed)

    assert cap.poll({})["captured"] == 2
    assert cap.poll({})["captured"] == 0           # deduped on the second pass
    got = cap.recent(device_id="dev-1")
    assert len(got) == 2 and {g["text"] for g in got} == {"code 111111", "code 222222"}


def test_wait_for_notification_extracts_group(fresh_db, monkeypatch):
    client = _client(with_capable_device=True)
    client.install_builtin_extension(SLUG)
    cap = _capmod()
    calls = {"n": 0}

    def fake_fetch(device_id):
        calls["n"] += 1
        # First call = baseline (empty); the OTP arrives on the next poll.
        return [] if calls["n"] == 1 else [
            {"package": "com.sms", "title": "Verify", "text": "Your code is 654321", "timestamp": 9}]

    monkeypatch.setattr(cap, "fetch_notifications", fake_fetch)
    assert cap.wait_for_match("dev-1", r"code is (\d{6})", timeout=5) == "654321"

    # And through the step type (result becomes the step output → run variable via store_as).
    calls["n"] = 0
    out = client._execute_step(
        {"type": "wait_for_notification", "config": {"pattern": r"(\d{6})", "timeout": 5}}, "dev-1")
    assert out == "654321"


def test_capture_forwards_to_bus_when_enabled(fresh_db, monkeypatch):
    client = _client(with_capable_device=True)
    client.install_builtin_extension(SLUG)
    client.update_extension_config(SLUG, {"forward_to_bus": True})
    cap = _capmod()
    monkeypatch.setattr(cap, "fetch_notifications",
                        lambda did: [{"package": "com.sms", "title": "Bank",
                                      "text": "code 424242", "timestamp": 5}])
    client.notify_calls.clear()
    assert cap.poll({})["captured"] == 1
    assert any(k == "notification.captured" for k, _ in client.notify_calls)


def test_capture_uninstall_purges(fresh_db):
    from sqlalchemy import inspect
    from devicekit.db import get_engine

    client = _client()
    client.install_builtin_extension(SLUG)
    assert f"ext_{PKG}_events" in inspect(get_engine()).get_table_names()
    client.uninstall_extension(SLUG, purge=True)
    names = inspect(get_engine()).get_table_names()
    assert f"ext_{PKG}_events" not in names
    # Schedule + seeded automation removed.
    assert not client.list_scheduled_jobs(owner_type="extension", owner_id=SLUG)
    assert not [a for a in client.list_automations() if f"ext:{SLUG}" in (a.get("tags") or [])]
