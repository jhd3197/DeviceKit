"""Plan 25 part 1 — the agent trust boundary: a fixed allowlist of read-only survey
primitives the server *composes*, never a raw shell command it *pushes*."""
import pytest

from devicekit import agent_primitives as ap
from devicekit.mixins.agent_survey import AgentSurveyMixin, SURVEY_COMMAND_PREFIX


# --------------------------------------------------------------------------- catalog
def test_catalog_is_all_read_only():
    cat = ap.list_primitives()
    assert cat["primitives"]
    assert all(spec["read_only"] for spec in cat["primitives"].values())


def test_allowlist_has_no_shell_or_whole_file_read():
    # The whole point of the boundary: no primitive can run a shell or exfiltrate a file.
    for banned in ("shell", "exec", "run", "cmd", "file.read", "file.pull", "cat", "su"):
        assert banned not in ap.PRIMITIVES


def test_expected_primitives_present():
    for name in ("file.exists", "fs.glob", "app.status", "app.list",
                 "process.list", "metrics.snapshot"):
        assert ap.is_primitive(name)


# --------------------------------------------------------------------------- validation
def test_validate_rejects_unknown_primitive():
    with pytest.raises(ap.PrimitiveError):
        ap.validate_primitive("shell", {"cmd": "rm -rf /"})


def test_validate_requires_required_arg():
    with pytest.raises(ap.PrimitiveError):
        ap.validate_primitive("file.exists", {})


def test_validate_applies_defaults_and_drops_unknown_args():
    out = ap.validate_primitive("fs.glob", {"pattern": "/sdcard/*", "bogus": 1})
    assert out == {"pattern": "/sdcard/*", "limit": 500}
    assert "bogus" not in out


def test_validate_type_checks_int_arg_rejects_bool():
    with pytest.raises(ap.PrimitiveError):
        ap.validate_primitive("fs.glob", {"pattern": "*", "limit": True})


def test_get_probe_unknown_raises():
    with pytest.raises(ap.PrimitiveError):
        ap.get_probe("does-not-exist")


def test_probes_only_name_allowlisted_primitives():
    for name in ap.COMPOSED_PROBES:
        recipe = ap.get_probe(name)
        assert all(ap.is_primitive(step["primitive"]) for step in recipe)


# --------------------------------------------------------------------------- composing side
class _FakeSurvey(AgentSurveyMixin):
    """Composer stubbed onto a fake command transport so we test dispatch, not a device."""

    def __init__(self):
        self.sent = []

    def send_device_command(self, device_id, command, args=None, timeout=None, source=None):
        self.sent.append({"device_id": device_id, "command": command,
                          "args": args, "source": source})
        # Simulate an offline device: send_device_command returns a failed row, never hangs.
        return {"id": f"cmd{len(self.sent)}", "command": command, "args": args,
                "status": "completed", "result": {"ok": True}, "error": None}


def test_send_agent_primitive_namespaces_the_command():
    c = _FakeSurvey()
    row = c.send_agent_primitive("dev1", "app.status", {"package": "com.x"})
    assert row["status"] == "completed"
    assert c.sent[0]["command"] == SURVEY_COMMAND_PREFIX + "app.status"
    assert c.sent[0]["args"] == {"package": "com.x"}
    assert c.sent[0]["source"] == "survey"


def test_send_agent_primitive_refuses_off_allowlist_before_dispatch():
    c = _FakeSurvey()
    with pytest.raises(ap.PrimitiveError):
        c.send_agent_primitive("dev1", "shell", {"cmd": "id"})
    assert c.sent == []  # nothing ever reached the transport


def test_compose_probe_runs_every_step_and_combines():
    c = _FakeSurvey()
    out = c.compose_agent_probe("dev1", "health")
    assert out["ok"] is True
    assert [s["primitive"] for s in out["steps"]] == ["metrics.snapshot", "app.status"]
    assert all(s["command"].startswith(SURVEY_COMMAND_PREFIX) for s in c.sent)


def test_compose_probe_reports_partial_failure_without_raising():
    class _Flaky(_FakeSurvey):
        def send_device_command(self, device_id, command, args=None, timeout=None, source=None):
            self.sent.append({"command": command})
            failed = command.endswith("app.status")
            return {"id": "x", "status": "failed" if failed else "completed",
                    "result": None, "error": "AGENT_OFFLINE" if failed else None}

    c = _Flaky()
    out = c.compose_agent_probe("dev1", "health")
    assert out["ok"] is False
    assert any(s["status"] == "failed" for s in out["steps"])
