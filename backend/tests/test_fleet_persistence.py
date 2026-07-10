"""Fleet groups, per-device tags, and saved FQL queries survive a restart."""
from devicekit.mixins.fleet import FleetMixin
from devicekit.mixins.fleet_query import FleetQueryMixin


class _Fleet(FleetMixin, FleetQueryMixin):
    """Minimal composition to exercise the fleet mixins without a full Client."""


def test_device_groups_survive_restart(fresh_db, restart):
    client = _Fleet()
    group = client.create_device_group(
        "Test Lab", description="phones", color="#ff0000",
        tags=["lab"], device_ids=["serialA"],
    )
    gid = group["id"]
    client.add_device_to_group(gid, "serialB")

    restart(fresh_db)

    reloaded = _Fleet()
    got = reloaded.get_device_group(gid)
    assert got is not None
    assert got["name"] == "Test Lab"
    assert set(got["device_ids"]) == {"serialA", "serialB"}
    assert got["tags"] == ["lab"]
    assert len(reloaded.list_device_groups()) == 1

    # membership query works post-restart
    assert reloaded.get_groups_for_device("serialB")[0]["id"] == gid


def test_group_delete_persists(fresh_db, restart):
    client = _Fleet()
    g = client.create_device_group("Temp")
    assert client.delete_device_group(g["id"]) is True
    assert client.delete_device_group(g["id"]) is False
    restart(fresh_db)
    assert _Fleet().get_device_group(g["id"]) is None


def test_device_tags_survive_restart(fresh_db, restart):
    client = _Fleet()
    client.set_device_tags("serialA", ["qa", "flaky"])
    restart(fresh_db)
    reloaded = _Fleet()
    assert reloaded.get_device_tags("serialA") == ["qa", "flaky"]
    # overwrite replaces, not appends
    reloaded.set_device_tags("serialA", ["prod"])
    assert reloaded.get_device_tags("serialA") == ["prod"]
    assert reloaded.get_device_tags("unknown") == []


def test_saved_queries_survive_restart(fresh_db, restart):
    client = _Fleet()
    q = client.create_saved_query("Low battery", "battery < 20", description="watch")
    qid = q["id"]

    # invalid expression is rejected
    try:
        client.create_saved_query("bad", "battery <<< 20")
        assert False, "expected ValueError"
    except ValueError:
        pass

    restart(fresh_db)

    reloaded = _Fleet()
    got = reloaded.get_saved_query(qid)
    assert got["expression"] == "battery < 20"
    assert len(reloaded.list_saved_queries()) == 1

    updated = reloaded.update_saved_query(qid, {"expression": "battery < 10"})
    assert updated["expression"] == "battery < 10"
    assert reloaded.delete_saved_query(qid) is True
    assert reloaded.get_saved_query(qid) is None
