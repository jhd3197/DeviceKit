"""The MCP server surface (plan 21, part 3) — no network, no running backend.

Covers the curated tool set registered on the FastMCP instance, the request shapes the
tool functions produce (by monkeypatching the module's ``_request`` helper), and the
startup key validation. Config is read lazily from env, so importing the module is safe
here and the invoke-timeout test can steer it per-test with ``monkeypatch.setenv``.
"""
import asyncio
import json

import pytest

from devicekit.mcp import server

CURATED_TOOLS = {
    "list_devices",
    "get_device_state",
    "query_fleet",
    "list_automations",
    "get_metrics",
    "run_automation",
    "send_command",
}


def _capture_requests(monkeypatch, response):
    """Swap ``server._request`` for a recorder returning ``response``; yields the calls."""
    calls = []

    def fake_request(method, path, params=None, body=None, timeout=server.READ_TIMEOUT):
        calls.append({"method": method, "path": path, "params": params,
                      "body": body, "timeout": timeout})
        return response

    monkeypatch.setattr(server, "_request", fake_request)
    return calls


# ------------------------------------------------------------------- the curated set

def test_exposes_exactly_the_seven_curated_tools():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == CURATED_TOOLS
    assert len(tools) == len(CURATED_TOOLS)  # no duplicate registrations
    # Docstrings are the tool descriptions the model sees — they must exist.
    assert all(t.description for t in tools)


def test_write_tool_descriptions_carry_the_gate_warning():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("send_command", "run_automation"):
        assert "block" in tools[name].description.lower()
        assert "DENIED" in tools[name].description


# ------------------------------------------------------------------- tool functions

def test_list_devices_returns_fleet_json(monkeypatch):
    fleet = {"devices": [{"serial": "emu-1", "model": "Pixel Test"}], "count": 1}
    calls = _capture_requests(monkeypatch, json.dumps(fleet, separators=(",", ":")))
    out = server.list_devices()
    assert json.loads(out) == fleet
    assert calls == [{"method": "GET", "path": "/api/v1/devices", "params": None,
                      "body": None, "timeout": server.READ_TIMEOUT}]


def test_send_command_posts_gated_invoke_body(monkeypatch):
    monkeypatch.setenv("DEVICEKIT_MCP_INVOKE_TIMEOUT", "120")
    reply = {"device_id": "emu-1", "action": "tap",
             "result": "Tapped at (10, 20)", "status": "ok"}
    calls = _capture_requests(monkeypatch, json.dumps(reply, separators=(",", ":")))
    out = server.send_command("emu-1", "tap", {"x": 10, "y": 20})
    assert calls == [{
        "method": "POST",
        "path": "/api/v1/actions/invoke",
        "params": None,
        "body": {"device_id": "emu-1", "action": "tap", "args": {"x": 10, "y": 20}},
        "timeout": 120.0,  # gated writes honor DEVICEKIT_MCP_INVOKE_TIMEOUT
    }]
    assert json.loads(out)["result"] == "Tapped at (10, 20)"
    assert json.loads(out)["status"] == "ok"


def test_send_command_defaults_args_to_empty_object(monkeypatch):
    calls = _capture_requests(monkeypatch, '{"status":"ok"}')
    server.send_command("emu-1", "reboot_device")
    assert calls[0]["body"] == {"device_id": "emu-1", "action": "reboot_device",
                                "args": {}}


def test_get_metrics_routes_device_vs_fleet(monkeypatch):
    calls = _capture_requests(monkeypatch, '{"points":[]}')
    server.get_metrics("battery_pct", device_id="emu-1", period="7d")
    server.get_metrics("battery_pct")
    assert calls[0]["path"] == "/api/v1/devices/emu-1/metrics"
    assert calls[0]["params"] == {"metric": "battery_pct", "period": "7d"}
    assert calls[1]["path"] == "/api/v1/fleet/metrics"
    assert calls[1]["params"] == {"metric": "battery_pct", "period": "24h"}


def test_run_automation_invokes_with_long_timeout(monkeypatch):
    monkeypatch.delenv("DEVICEKIT_MCP_INVOKE_TIMEOUT", raising=False)
    reply = {"device_id": "emu-1", "action": "run_automation",
             "result": "DENIED: confirmation timed out", "status": "denied"}
    calls = _capture_requests(monkeypatch, json.dumps(reply, separators=(",", ":")))
    out = server.run_automation("auto-7", "emu-1")
    assert calls[0]["path"] == "/api/v1/actions/invoke"
    assert calls[0]["body"] == {"device_id": "emu-1", "action": "run_automation",
                                "args": {"automation_id": "auto-7"}}
    assert calls[0]["timeout"] == float(server.DEFAULT_INVOKE_TIMEOUT)
    assert json.loads(out)["status"] == "denied"  # DENIED strings pass through verbatim


# ------------------------------------------------------------------ startup validation

@pytest.mark.parametrize("key", [None, "", "sk-not-a-devicekit-key"])
def test_main_refuses_missing_or_foreign_key(monkeypatch, capsys, key):
    if key is None:
        monkeypatch.delenv("DEVICEKIT_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DEVICEKIT_API_KEY", key)
    with pytest.raises(SystemExit) as exc:
        server.main(["--transport", "stdio"])
    assert exc.value.code == 2
    assert "DEVICEKIT_API_KEY" in capsys.readouterr().err
