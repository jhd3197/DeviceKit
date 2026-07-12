"""Plan 25 part 2 — capability normalization, version advertisement, batched-vs-composed
survey negotiation, and the fleet 'which agent version where' rollup."""
import threading

from devicekit.agent_capabilities import (
    normalize_capabilities, supports_batch_survey, extract_agent_version)
from devicekit.mixins.agent_device import AgentDeviceMixin
from devicekit.mixins.agent_survey import AgentSurveyMixin


# --------------------------------------------------------------- capability normalization
def test_legacy_array_becomes_map():
    out = normalize_capabilities(["accessibility", "metrics_collection"])
    assert out == {"accessibility": True, "metrics_collection": True}


def test_map_is_passed_through():
    raw = {"screen_record": True, "android_api": 34}
    assert normalize_capabilities(raw) == raw


def test_none_and_junk_become_empty_map():
    assert normalize_capabilities(None) == {}
    assert normalize_capabilities("nope") == {}


def test_supports_batch_survey():
    assert supports_batch_survey({"batch_survey": True})
    assert not supports_batch_survey({"accessibility": True})
    assert not supports_batch_survey({})


def test_extract_agent_version():
    assert extract_agent_version({"agent_version": "1.2.0", "agent_version_code": 5}) == ("1.2.0", 5)
    assert extract_agent_version({"agent_version": "1.0.0"}) == ("1.0.0", None)
    assert extract_agent_version({"agent_version_code": "bad"}) == (None, None)
    assert extract_agent_version({}) == (None, None)


# ------------------------------------------------------------------- register persists both
class _Agent(AgentDeviceMixin):
    pass


def test_register_normalizes_caps_and_persists_version(fresh_db, restart):
    client = _Agent()
    client.init_agent_registry()
    info = {"model": "SM-S134DL", "manufacturer": "samsung",
            "agent_version": "1.3.0", "agent_version_code": 7,
            # legacy array shape straight off the current APK:
            "capabilities": ["accessibility", "metrics_collection"]}
    client.register_agent_device("samsung_SM-S134DL", info=info, serial="R9TT311P25N",
                                 capabilities=info["capabilities"])
    caps = client.get_agent_capabilities("samsung_SM-S134DL")
    assert caps == {"accessibility": True, "metrics_collection": True}

    restart(fresh_db)
    reloaded = _Agent()
    reloaded.init_agent_registry()
    rows = reloaded.load_agent_devices()
    assert rows[0]["agent_version"] == "1.3.0"
    assert rows[0]["agent_version_code"] == 7
    assert rows[0]["capabilities"] == {"accessibility": True, "metrics_collection": True}


def test_reregister_without_version_keeps_known_version(fresh_db):
    client = _Agent()
    client.init_agent_registry()
    client.register_agent_device(
        "d1", info={"agent_version": "2.0.0", "agent_version_code": 9}, serial="s1")
    # A legacy re-register that omits version must not blank the known one.
    client.register_agent_device("d1", info={"model": "x"}, serial="s1")
    rows = {r["device_id"]: r for r in client.load_agent_devices()}
    assert rows["d1"]["agent_version"] == "2.0.0"
    assert rows["d1"]["agent_version_code"] == 9


# ------------------------------------------------------------------------ version rollup
class _Reg(AgentDeviceMixin):
    def __init__(self, states):
        self._agent_device_states = states
        self._agent_registry_lock = threading.RLock()


def test_list_agent_versions_rollup():
    reg = _Reg({
        "d1": {"device_id": "d1", "agent_version": "1.0.0", "agent_version_code": 1,
               "online": True, "info": {"model": "A"}, "capabilities": {"android_api": 33}},
        "d2": {"device_id": "d2", "agent_version": "1.0.0", "agent_version_code": 1,
               "online": False, "info": {"model": "B"}, "capabilities": {}},
        "d3": {"device_id": "d3", "agent_version": "1.1.0", "agent_version_code": 2,
               "online": True, "info": {"model": "C"}, "capabilities": {}},
    })
    out = reg.list_agent_versions()
    assert out["distinct_versions"] == 2
    versions = {v["version"]: v for v in out["versions"]}
    assert versions["1.0.0"]["count"] == 2
    assert versions["1.0.0"]["online"] == 1
    assert set(versions["1.0.0"]["device_ids"]) == {"d1", "d2"}
    assert versions["1.1.0"]["count"] == 1


def test_list_agent_versions_unknown_bucket():
    reg = _Reg({"d1": {"device_id": "d1", "agent_version": None,
                       "online": True, "info": {}, "capabilities": {}}})
    out = reg.list_agent_versions()
    assert out["versions"][0]["version"] == "unknown"


# --------------------------------------------------------------- batched vs composed survey
class _Survey(AgentSurveyMixin):
    def __init__(self, caps, batch_result=None, fail_batch=False):
        self.caps = caps
        self.commands = []
        self.batch_result = batch_result
        self.fail_batch = fail_batch

    def get_agent_capabilities(self, device_id):
        return self.caps

    def send_device_command(self, device_id, command, args=None, timeout=None, source=None):
        self.commands.append(command)
        if command == "survey.batch":
            if self.fail_batch:
                return {"status": "failed", "error": "AGENT_OFFLINE"}
            return {"status": "completed", "result": self.batch_result}
        return {"status": "completed", "result": {"ok": True}}


_GOOD_BATCH = {"results": [
    {"primitive": "metrics.snapshot", "result": {"cpu": 3}},
    {"primitive": "app.status", "result": {"installed": True}},
]}


def test_batch_capable_agent_uses_one_command():
    c = _Survey({"batch_survey": True}, batch_result=_GOOD_BATCH)
    out = c.compose_agent_probe("d1", "health")
    assert out["transport"] == "batched"
    assert out["ok"] is True
    assert c.commands == ["survey.batch"]


def test_non_batch_agent_uses_composed_path():
    c = _Survey({"accessibility": True})
    out = c.compose_agent_probe("d1", "health")
    assert out["transport"] == "composed"
    assert c.commands == ["survey.metrics.snapshot", "survey.app.status"]


def test_batch_failure_falls_back_to_composed():
    c = _Survey({"batch_survey": True}, fail_batch=True)
    out = c.compose_agent_probe("d1", "health")
    assert out["transport"] == "composed"
    assert c.commands[0] == "survey.batch"
    assert "survey.metrics.snapshot" in c.commands


def test_batch_malformed_result_falls_back():
    c = _Survey({"batch_survey": True}, batch_result={"unexpected": "shape"})
    out = c.compose_agent_probe("d1", "health")
    assert out["transport"] == "composed"
