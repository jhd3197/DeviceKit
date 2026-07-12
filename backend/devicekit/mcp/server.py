"""FastMCP server over DeviceKit's scoped ``/api/v1`` surface (plan 21, part 3).

Seven curated tools, not raw route parity: five reads that run free and two writes that
route through the gated ``POST /api/v1/actions/invoke`` — meaning a write call can block
for *minutes* while a human approves it in the DeviceKit UI (see the package docstring
for the full safety story). Tool docstrings double as the MCP tool descriptions, so they
are written for the model on the other end.

Configuration is read lazily from the environment (importing this module never fails):

* ``DEVICEKIT_URL`` — backend base URL (default ``http://127.0.0.1:5050``).
* ``DEVICEKIT_API_KEY`` — required ``dk_`` key; validated at startup in :func:`main`.
* ``DEVICEKIT_MCP_INVOKE_TIMEOUT`` — seconds to wait on a gated invoke (default 900).

Every tool returns a compact string — a minified JSON dump on success, or an
``ERROR <status>: <body>`` / ``ERROR: <exception>`` string on failure. Tools never raise:
an MCP client should always get *something* it can show the model.
"""
import argparse
import json
import os
import sys

import requests
from mcp.server.fastmcp import FastMCP

DEFAULT_URL = "http://127.0.0.1:5050"
DEFAULT_INVOKE_TIMEOUT = 900  # seconds a gated write may wait on human approval
READ_TIMEOUT = 30             # seconds for plain read endpoints

mcp = FastMCP(
    "devicekit",
    instructions=(
        "Tools for the DeviceKit Android fleet. Reads (list_devices, get_device_state, "
        "query_fleet, list_automations, get_metrics) run immediately. Writes "
        "(send_command, run_automation) are gated: the call blocks until a human "
        "approves it in the DeviceKit UI, and a result starting with 'DENIED' means the "
        "approval was declined, timed out, or the device is read-only (observe mode)."
    ),
)


# ---------------------------------------------------------------- config (lazy, env-read)

def _base_url():
    """Backend base URL, trailing slash stripped so path-joins stay predictable."""
    return os.environ.get("DEVICEKIT_URL", DEFAULT_URL).rstrip("/")


def _api_key():
    """The ``dk_`` key sent as ``X-API-Key`` on every call (validated in :func:`main`)."""
    return os.environ.get("DEVICEKIT_API_KEY", "")


def _invoke_timeout():
    """Seconds a gated invoke may block awaiting human approval."""
    try:
        return float(os.environ.get("DEVICEKIT_MCP_INVOKE_TIMEOUT", DEFAULT_INVOKE_TIMEOUT))
    except ValueError:
        return float(DEFAULT_INVOKE_TIMEOUT)


# ---------------------------------------------------------------------------- HTTP helper

def _request(method, path, params=None, body=None, timeout=READ_TIMEOUT):
    """One authenticated round-trip to the backend; errors come back as strings.

    Success responses are re-dumped as minified JSON (non-JSON bodies pass through
    verbatim). HTTP errors become ``ERROR <status>: <body>`` and transport failures
    ``ERROR: <exception>`` — never an exception, so every tool degrades to a message
    the model can read and act on.
    """
    try:
        resp = requests.request(
            method, _base_url() + path, params=params, json=body,
            headers={"X-API-Key": _api_key()}, timeout=timeout)
    except requests.RequestException as e:
        return f"ERROR: {e}"
    if resp.status_code >= 400:
        return f"ERROR {resp.status_code}: {resp.text.strip()}"
    try:
        return json.dumps(resp.json(), separators=(",", ":"))
    except ValueError:
        return resp.text


# ------------------------------------------------------------------------- read tools

@mcp.tool()
def list_devices() -> str:
    """List every device in the DeviceKit fleet.

    Returns JSON {"devices": [...], "count": N}. Each device has a "serial" (use it as
    the device_id for every other tool), plus model, manufacturer, android_version,
    online, source ("adb" or "agent"), and live metrics like battery_level and
    cpu_percent when available. Call this first to discover device ids.

    Requires scope: devices:read.
    """
    return _request("GET", "/api/v1/devices")


@mcp.tool()
def get_device_state(device_id: str) -> str:
    """Fetch live diagnostics for one device.

    Returns JSON with battery_level, temperature, cpu_percent, mem_used_mb /
    mem_total_mb, is_charging, network type and rates, and "source" — "agent" when a
    fresh agent heartbeat exists, otherwise ADB-sourced. Use list_devices to find valid
    device ids.

    Requires scope: devices:read.
    """
    return _request("GET", f"/api/v1/devices/{device_id}/diagnostics")


@mcp.tool()
def query_fleet(fql: str) -> str:
    """Run a Fleet Query Language (FQL) expression across all devices.

    Example: "battery < 20 AND online = true". Fields include battery, online, model,
    manufacturer, android_version, cpu, source; operators =, !=, <, >, <=, >=, AND, OR,
    NOT. Returns JSON {"matches": [...], "count": N, "total": M, "expression": "..."}
    where matches are full device rows and total is the fleet size.

    Requires scope: devices:read.
    """
    return _request("GET", "/api/v1/fleet/query", params={"q": fql})


@mcp.tool()
def list_automations() -> str:
    """List saved automations (recorded or authored step sequences).

    Returns JSON {"automations": [...], "count": N}; each automation has an "id",
    "name", "description", and its steps. Use an automation's id with run_automation
    to execute it on a device.

    Requires scope: automations:read.
    """
    return _request("GET", "/api/v1/automations")


@mcp.tool()
def get_metrics(metric: str, device_id: str = "", period: str = "24h") -> str:
    """Query recorded metric history for one device or the whole fleet.

    With device_id: that device's time series. Without: an aligned fleet-wide series.
    metric is a catalog name such as battery_pct, battery_temp, cpu_percent,
    ram_used_mb, or storage_used_pct (GET /api/v1/metrics/catalog lists them all);
    period is one of 1h, 24h, 7d, 30d. Returns JSON with the sampled points.

    Requires scope: metrics:read.
    """
    params = {"metric": metric, "period": period}
    if device_id:
        return _request("GET", f"/api/v1/devices/{device_id}/metrics", params=params)
    return _request("GET", "/api/v1/fleet/metrics", params=params)


# ---------------------------------------------------------------- write tools (gated)

@mcp.tool()
def run_automation(automation_id: str, device_id: str) -> str:
    """Run a saved automation on a device (gated write — may block for minutes).

    This waits for a human to approve the run in the DeviceKit UI unless the API key
    holds the mcp:autonomous opt-in and the device is in autonomous mode. Returns JSON
    {"device_id", "action", "result", "status"}: status "ok" with a queued-run id in
    result on approval; status "denied" with a result starting with "DENIED" when the
    approval was declined, timed out, or the device is in observe mode. Find ids with
    list_automations and list_devices.

    Requires scope: automations:run.
    """
    return _request(
        "POST", "/api/v1/actions/invoke",
        body={"device_id": device_id, "action": "run_automation",
              "args": {"automation_id": automation_id}},
        timeout=_invoke_timeout())


@mcp.tool()
def send_command(device_id: str, action: str, args: dict | None = None) -> str:
    """Execute one curated device action (gated write — may block for minutes).

    The call BLOCKS until a human approves it in the DeviceKit UI (or the gate times
    out), unless the key holds mcp:autonomous and the device is in autonomous mode.
    Valid actions and their args:

    - tap {"x": int, "y": int} — tap screen coordinates
    - swipe {"direction": "up"|"down"|"left"|"right"} — swipe the screen
    - type_text {"text": str} — type into the focused input field
    - press_key {"key": "home"|"back"|"enter"|"recent"} — press a device key
    - open_app {"package": str} — launch an app by package name
    - uninstall_app {"package": str} — uninstall an app by package name
    - adb_shell {"command": str} — run an adb shell command
    - reboot_device {} — reboot the device

    Returns JSON {"device_id", "action", "result", "status"}; status "denied" with a
    result starting with "DENIED" means declined, timed out, or observe mode. GET
    /api/v1/actions lists the same registry with full JSON schemas.

    Requires scope: devices:command.
    """
    return _request(
        "POST", "/api/v1/actions/invoke",
        body={"device_id": device_id, "action": action, "args": args or {}},
        timeout=_invoke_timeout())


# --------------------------------------------------------------------------- entrypoint

def main(argv=None):
    """Parse transport flags, validate the API key, and run the server (blocking)."""
    parser = argparse.ArgumentParser(
        prog="python -m devicekit.mcp",
        description="DeviceKit MCP server: curated fleet tools over the scoped "
                    "/api/v1 HTTP API. Requires DEVICEKIT_API_KEY (a dk_ key); "
                    "DEVICEKIT_URL points at the backend "
                    f"(default {DEFAULT_URL}).")
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"], default="stdio",
        help="MCP transport: stdio for local clients (default), "
             "streamable-http to serve HTTP at /mcp.")
    parser.add_argument(
        "--host", default=None,
        help="Bind host for --transport streamable-http (default 127.0.0.1).")
    parser.add_argument(
        "--port", type=int, default=None,
        help="Bind port for --transport streamable-http (default 8000).")
    args = parser.parse_args(argv)

    key = _api_key()
    if not key.startswith("dk_"):
        print("devicekit-mcp: DEVICEKIT_API_KEY must be set to a DeviceKit API key "
              "(dk_...). Mint one in the DeviceKit UI under Settings > API Keys; "
              "see docs/mcp-server.md for the recommended scope sets.",
              file=sys.stderr)
        sys.exit(2)

    # FastMCP reads host/port from its settings object; flags override the defaults.
    if args.host is not None:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
