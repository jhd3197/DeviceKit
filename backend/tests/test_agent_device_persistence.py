"""Registered agent devices survive a restart (the api_app closure re-hydrates from DB)."""
from devicekit.mixins.agent_device import AgentDeviceMixin


class _Agent(AgentDeviceMixin):
    pass


def test_agent_device_registry_survives_restart(fresh_db, restart):
    client = _Agent()
    info = {"model": "SM-S134DL", "manufacturer": "samsung", "serial": "R9TT311P25N"}
    client.save_agent_device(
        "samsung_SM-S134DL", info=info, serial="R9TT311P25N",
        registered_at=100.0, last_heartbeat=100.0, state={}, online=True,
    )
    # a metrics state update writes through
    client.update_agent_device_fields(
        "samsung_SM-S134DL", state={"metrics": {"battery_level": 80}},
        last_heartbeat=105.0, online=True,
    )

    restart(fresh_db)

    reloaded = _Agent()
    rows = reloaded.load_agent_devices()
    assert len(rows) == 1
    row = rows[0]
    assert row["device_id"] == "samsung_SM-S134DL"
    assert row["serial"] == "R9TT311P25N"
    assert row["info"]["model"] == "SM-S134DL"
    assert row["state"]["metrics"]["battery_level"] == 80
    assert row["online"] is True

    # stale → offline persists
    reloaded.update_agent_device_fields("samsung_SM-S134DL", online=False)
    assert reloaded.load_agent_devices()[0]["online"] is False

    # unknown device update is a no-op
    assert reloaded.update_agent_device_fields("nope", online=True) is False
