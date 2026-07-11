"""Automations, schedules, and runs survive a restart."""
from devicekit.mixins.automation import AutomationMixin


class _Auto(AutomationMixin):
    """Exercise the automation mixin's persistence without device execution."""


def _steps():
    return [
        {"id": "s1", "type": "wait", "label": "wait", "config": {"delay": 10}},
        {"id": "s2", "type": "screenshot", "label": "shot", "config": {}},
    ]


def test_automations_survive_restart(fresh_db, restart):
    client = _Auto()
    a = client.create_automation("Login flow", description="d", steps=_steps(), tags=["smoke"])
    aid = a["id"]

    restart(fresh_db)

    reloaded = _Auto()
    got = reloaded.get_automation(aid)
    assert got is not None
    assert got["name"] == "Login flow"
    assert len(got["steps"]) == 2
    assert got["tags"] == ["smoke"]
    assert len(reloaded.list_automations()) == 1

    updated = reloaded.update_automation(aid, {"name": "Login v2"})
    assert updated["name"] == "Login v2"
    assert updated["updated_at"] >= got["updated_at"]


def test_clone_and_export(fresh_db):
    client = _Auto()
    a = client.create_automation("Base", steps=_steps())
    clone = client.clone_automation(a["id"])
    assert clone["id"] != a["id"]
    assert clone["name"] == "Base (Copy)"
    # cloned steps get fresh ids
    assert {s["id"] for s in clone["steps"]}.isdisjoint({s["id"] for s in a["steps"]})
    assert len(client.list_automations()) == 2

    exported = client.export_automation(a["id"])
    assert "id" not in exported
    imported = client.import_automation(exported)
    assert imported["name"] == "Base"
    assert len(client.list_automations()) == 3


def test_delete_automation(fresh_db, restart):
    client = _Auto()
    a = client.create_automation("Doomed")
    assert client.delete_automation(a["id"]) is True
    assert client.delete_automation(a["id"]) is False
    restart(fresh_db)
    assert _Auto().get_automation(a["id"]) is None


def test_schedules_survive_restart(fresh_db, restart):
    client = _Auto()
    a = client.create_automation("Nightly")
    sch = client.create_schedule(a["id"], "serialA", interval_minutes=60, enabled=True)
    sid = sch["id"]
    assert sch["next_run_at"] > sch["created_at"]

    restart(fresh_db)

    reloaded = _Auto()
    got = reloaded.get_schedule(sid)
    assert got is not None
    assert got["automation_id"] == a["id"]
    assert got["enabled"] is True
    assert len(reloaded.list_schedules()) == 1
    assert len(reloaded.list_schedules(automation_id=a["id"])) == 1

    reloaded.update_schedule(sid, {"enabled": False})
    assert reloaded.get_schedule(sid)["enabled"] is False
    assert reloaded.delete_schedule(sid) is True
    assert reloaded.get_schedule(sid) is None


def test_runs_persist_and_survive_restart(fresh_db, restart):
    client = _Auto()
    a = client.create_automation("R")
    # Directly persist a run record (skipping device execution) via the same helper the
    # run thread uses.
    run = {
        "id": "run-1",
        "automation_id": a["id"],
        "automation_name": "R",
        "device_id": "serialA",
        "status": "completed",
        "started_at": 100.0,
        "finished_at": 105.0,
        "total_steps": 2,
        "completed_steps": 2,
        "current_step_index": 2,
        "step_results": [{"step_id": "s1", "status": "completed"}],
        "error": None,
        "self_heal": False,
    }
    client._save_run(run)
    # update in place (simulates progress writes)
    run["status"] = "failed"
    run["error"] = "boom"
    client._save_run(run)

    restart(fresh_db)

    reloaded = _Auto()
    got = reloaded.get_automation_run("run-1")
    assert got["status"] == "failed"
    assert got["error"] == "boom"
    assert got["step_results"][0]["step_id"] == "s1"
    runs = reloaded.list_automation_runs(automation_id=a["id"])
    assert len(runs) == 1
    assert reloaded.list_automation_runs(device_id="serialA")[0]["id"] == "run-1"
