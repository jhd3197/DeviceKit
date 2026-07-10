"""Plan 07 phase 1 — hardened agent registry: reconnect correctness, the heartbeat reaper
(offline exactly once, no flap on reconnect), and the DeviceCommand audit trail."""
import time
import threading

from devicekit.mixins.agent_device import AgentDeviceMixin
from devicekit.models import DeviceCommand


class _Agent(AgentDeviceMixin):
    """Minimal composite: capture broadcasts/notifications instead of fanning out."""

    def __init__(self):
        self.events = []
        self.notifications = []
        self.init_agent_registry()

    def broadcast(self, event, data):
        self.events.append((event, data))

    def notify_event(self, key, **kwargs):
        self.notifications.append((key, kwargs))

    def log_activity(self, *a, **k):
        pass


def test_register_is_reconnect_aware(fresh_db):
    c = _Agent()
    r1 = c.register_agent_device("samsung_a03s", info={"model": "A03s"}, serial="R9T")
    assert r1["reconnected"] is False
    r2 = c.register_agent_device("samsung_a03s", info={"model": "A03s"}, serial="R9T")
    assert r2["reconnected"] is True
    # conn_token advances so a stale timeout can't clobber a fresh connection
    assert r2["conn_token"] > r1["conn_token"]


def test_reconnect_fails_inflight_commands(fresh_db):
    c = _Agent()
    c.register_agent_device("dev1", info={"model": "X"})

    results = {}

    def dispatch():
        results["row"] = c.send_device_command("dev1", "screenshot", timeout=5)

    t = threading.Thread(target=dispatch)
    t.start()
    # Let the command register as in-flight, then reconnect the device.
    time.sleep(0.3)
    c.register_agent_device("dev1", info={"model": "X"})
    t.join(timeout=5)

    assert results["row"]["status"] == DeviceCommand.STATUS_FAILED
    assert results["row"]["error"] == "AGENT_RECONNECTED"


def test_command_dispatch_audit_trail(fresh_db):
    c = _Agent()
    c.register_agent_device("dev2", info={"model": "Y"})

    results = {}

    def dispatch():
        results["row"] = c.send_device_command("dev2", "tap", args={"x": 1}, timeout=5)

    t = threading.Thread(target=dispatch)
    t.start()
    time.sleep(0.3)

    # Agent polls, gets the command, posts a result back.
    pending = c.drain_outbound_commands("dev2")
    assert len(pending) == 1
    assert pending[0]["command"] == "tap"
    c.resolve_device_command(pending[0]["id"], result={"ok": True})
    t.join(timeout=5)

    row = results["row"]
    assert row["status"] == DeviceCommand.STATUS_COMPLETED
    assert row["result"] == {"ok": True}
    # persisted + queryable
    history = c.list_device_commands(device_id="dev2")
    assert len(history) == 1
    assert history[0]["command"] == "tap"


def test_command_times_out_when_agent_silent(fresh_db):
    c = _Agent()
    c.register_agent_device("dev3", info={"model": "Z"})
    row = c.send_device_command("dev3", "noop", timeout=0.5)
    assert row["status"] == DeviceCommand.STATUS_TIMEOUT


def test_dispatch_to_offline_device_fails_fast(fresh_db):
    c = _Agent()
    # Never registered / not online
    c._agent_device_states["ghost"] = {
        "device_id": "ghost", "online": False, "conn_token": 0,
        "last_heartbeat": 0, "info": {}, "state": {},
    }
    c.save_agent_device("ghost", info={}, online=False)
    row = c.send_device_command("ghost", "tap", timeout=1)
    assert row["status"] == DeviceCommand.STATUS_FAILED
    assert row["error"] == "AGENT_OFFLINE"


def test_reaper_marks_offline_exactly_once_and_no_flap(fresh_db):
    c = _Agent()
    c.register_agent_device("dev4", info={"model": "Q"})
    # Age the heartbeat past the timeout.
    c._agent_device_states["dev4"]["last_heartbeat"] = time.time() - 200

    evicted = c.reap_stale_agents(timeout=90)
    assert evicted == ["dev4"]
    offline_notifs = [n for n in c.notifications if n[0] == "device.offline"]
    assert len(offline_notifs) == 1

    # Second sweep: already offline → no second notification (exactly once).
    evicted2 = c.reap_stale_agents(timeout=90)
    assert evicted2 == []
    assert len([n for n in c.notifications if n[0] == "device.offline"]) == 1

    # A quick reconnect refreshes the heartbeat; the next sweep must NOT evict it.
    c.register_agent_device("dev4", info={"model": "Q"})
    assert c.reap_stale_agents(timeout=90) == []
    assert c._agent_device_states["dev4"]["online"] is True
