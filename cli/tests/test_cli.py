"""Tests for the generated-client toolchain (plan 21 phase 4).

Covers the parts that must stay stable: the deterministic method-name derivation, the
generator's collision guard, the client's error handling, and the CLI wiring end to end
against a stubbed transport. No network, no running backend.
"""
import json
import sys
from pathlib import Path

import pytest

_CLI_DIR = Path(__file__).resolve().parent.parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import generate_client as gen
from devicekit_cli.client import DeviceKitApiError, DeviceKitClient
from devicekit_cli import main as cli_main


# ------------------------------------------------------------- name derivation
@pytest.mark.parametrize("verb,path,expected", [
    ("get", "/api/v1/devices", "get_devices"),
    ("get", "/api/v1", "get_index"),
    ("get", "/api/v1/devices/{device_id}/diagnostics",
     "get_devices_by_device_id_diagnostics"),
    ("post", "/api/v1/automations/{automation_id}/run",
     "post_automations_by_automation_id_run"),
    ("get", "/api/v1/openapi.json", "get_openapi_json"),
    ("post", "/api/v1/actions/invoke", "post_actions_invoke"),
])
def test_method_name(verb, path, expected):
    assert gen.method_name(verb, path) == expected


def test_path_params_order():
    assert gen.path_params("/api/v1/a/{x}/b/{y}") == ["x", "y"]


def test_generate_flags_collisions():
    spec = {"info": {"title": "T", "version": "v1"}, "paths": {
        "/api/v1/x": {"get": {"summary": "a"}},
        "/api/v1/x/": {"get": {"summary": "b"}},  # both derive get_x
    }}
    with pytest.raises(ValueError, match="collision"):
        gen.generate(spec)


def test_generated_source_is_importable_and_deterministic():
    spec = {"info": {"title": "T", "version": "v1"}, "paths": {
        "/api/v1/devices": {"get": {"summary": "List devices"}},
        "/api/v1/devices/{device_id}/tap": {
            "post": {"summary": "Tap", "x-required-scope": "devices:command"}},
    }}
    src1, count = gen.generate(spec)
    src2, _ = gen.generate(spec)
    assert src1 == src2 and count == 2
    ns = {}
    exec(compile(src1, "<generated>", "exec"), ns)
    client = ns["DeviceKitClient"]("http://x")
    assert hasattr(client, "get_devices")
    assert hasattr(client, "post_devices_by_device_id_tap")
    assert "devices:command" in client.post_devices_by_device_id_tap.__doc__


def test_snapshot_regenerates_to_the_committed_client():
    """The committed client.py must be exactly what the snapshot produces."""
    spec = json.loads((_CLI_DIR / "openapi.snapshot.json").read_text(encoding="utf-8"))
    source, _ = gen.generate(spec)
    committed = (_CLI_DIR / "devicekit_cli" / "client.py").read_text(encoding="utf-8")
    assert source == committed, "client.py is stale — rerun generate_client.py"


# ------------------------------------------------------------------ client I/O
class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.reason = "reason"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Session:
    def __init__(self, resp):
        self.resp = resp
        self.headers = {}
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url, params, json))
        return self.resp


def _client_with(resp):
    c = DeviceKitClient("http://bk", api_key="dk_test")
    c.session = _Session(resp)
    return c


def test_client_sends_api_key_header():
    c = DeviceKitClient("http://bk", api_key="dk_abc")
    assert c.session.headers["X-API-Key"] == "dk_abc"


def test_client_returns_parsed_json():
    c = _client_with(_Resp(200, {"devices": [], "count": 0}))
    assert c.get_devices() == {"devices": [], "count": 0}
    method, url, params, _ = c.session.calls[0]
    assert method == "GET" and url == "http://bk/api/v1/devices"


def test_client_encodes_path_params():
    c = _client_with(_Resp(200, {"ok": True}))
    c.get_devices_by_device_id_diagnostics("a/b c")
    _, url, _, _ = c.session.calls[0]
    assert url == "http://bk/api/v1/devices/a%2Fb%20c/diagnostics"


def test_client_raises_api_error_with_server_message():
    c = _client_with(_Resp(403, {"error": "Missing required scope: devices:command"}))
    with pytest.raises(DeviceKitApiError) as ei:
        c.post_actions_invoke(json={"device_id": "d", "action": "tap"})
    assert ei.value.status == 403
    assert "devices:command" in ei.value.message


# --------------------------------------------------------------------- the CLI
def test_cli_devices_ls_renders_table(monkeypatch, capsys):
    from click.testing import CliRunner

    payload = {"devices": [
        {"device_id": "R9TT311P25N", "model": "SM-S134DL", "android_version": "13",
         "online": True, "battery_level": 84, "source": "adb"},
    ], "count": 1}
    monkeypatch.setattr(DeviceKitClient, "get_devices", lambda self, params=None: payload)
    result = CliRunner().invoke(cli_main.cli, ["devices", "ls"])
    assert result.exit_code == 0
    assert "R9TT311P25N" in result.output
    assert "84%" in result.output
    assert "1 device(s)" in result.output


def test_cli_api_error_exits_1(monkeypatch):
    from click.testing import CliRunner

    def boom(self, params=None):
        raise DeviceKitApiError(500, "no such column: automations.workspace_id")

    monkeypatch.setattr(DeviceKitClient, "get_automations", boom)
    result = CliRunner().invoke(cli_main.cli, ["automation", "ls"])
    assert result.exit_code == 1
    assert "workspace_id" in result.output
