# MCP Server

DeviceKit ships a first-class [Model Context Protocol](https://modelcontextprotocol.io) server
(`backend/devicekit/mcp/`) so any MCP client — Claude Code, Claude Desktop, or a custom agent —
can read fleet state and, with the right scopes, drive devices. It is a thin, curated layer over
the scoped `/api/v1` HTTP API: **seven tools**, five reads and two writes, and every write flows
through the same [confirmation gate](ai-agent.md#the-confirmation-gate) an in-app AI action gets.

The server itself holds no privileges. Everything it may do is decided by the `dk_` API key you
hand it — mint a narrow key and the write tools simply return a `403` error string.

## 1. Mint a scoped API key

In the DeviceKit UI: **Settings → API Keys → New Key**. Pick the scope set for how much you trust
the client on the other end:

| Intent | Scopes |
| --- | --- |
| **Read-only** (recommended start) | `devices:read`, `automations:read`, `metrics:read` |
| **Write** (gated device control) | read-only set + `devices:command`, `automations:run` |
| **Autonomous** (explicit opt-in) | write set + `mcp:autonomous` |

`mcp:autonomous` is deliberately never implied by `*` or `devices:*` wildcards — you hold the
exact token or you don't have it. Without it, every write from this key waits for a human, even
on a device whose agent mode is `autonomous`. With it, the device's mode decides, and the
auto-approval is audited like any other gate decision.

## 2. Configure the server

Configuration comes from the environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DEVICEKIT_URL` | `http://127.0.0.1:5050` | The DeviceKit backend to talk to. |
| `DEVICEKIT_API_KEY` | *(required)* | A `dk_` key; the server refuses to start without one. |
| `DEVICEKIT_MCP_INVOKE_TIMEOUT` | `900` | Seconds a gated write may block awaiting approval. |

### Claude Code

Drop a `.mcp.json` at the root of the project you're working in:

```json
{
  "mcpServers": {
    "devicekit": {
      "command": "python",
      "args": ["-m", "devicekit.mcp"],
      "cwd": "<repo>/backend",
      "env": {
        "DEVICEKIT_URL": "http://127.0.0.1:5050",
        "DEVICEKIT_API_KEY": "dk_..."
      }
    }
  }
}
```

### Claude Desktop

Claude Desktop's config (`Settings → Developer → Edit Config`, which opens
`claude_desktop_config.json`) has no `cwd` field, so point `PYTHONPATH` at the backend instead:

```json
{
  "mcpServers": {
    "devicekit": {
      "command": "python",
      "args": ["-m", "devicekit.mcp"],
      "env": {
        "PYTHONPATH": "<repo>/backend",
        "DEVICEKIT_URL": "http://127.0.0.1:5050",
        "DEVICEKIT_API_KEY": "dk_..."
      }
    }
  }
}
```

### Streamable HTTP

For remote clients, run the server as a standalone HTTP service (MCP's streamable-http
transport, served at `/mcp`):

```bash
DEVICEKIT_API_KEY=dk_... python -m devicekit.mcp \
    --transport streamable-http --host 127.0.0.1 --port 8765
```

Then point the client at `http://127.0.0.1:8765/mcp` (Claude Code:
`claude mcp add --transport http devicekit http://127.0.0.1:8765/mcp`). The API key stays on the
server side — the HTTP endpoint itself carries no auth, so bind it to localhost or a trusted
network only.

## The tools

| Tool | Backing endpoint | Required scope | Gated? |
| --- | --- | --- | --- |
| `list_devices` | `GET /api/v1/devices` | `devices:read` | No |
| `get_device_state` | `GET /api/v1/devices/<id>/diagnostics` | `devices:read` | No |
| `query_fleet` | `GET /api/v1/fleet/query?q=<fql>` | `devices:read` | No |
| `list_automations` | `GET /api/v1/automations` | `automations:read` | No |
| `get_metrics` | `GET /api/v1/devices/<id>/metrics` · `GET /api/v1/fleet/metrics` | `metrics:read` | No |
| `run_automation` | `POST /api/v1/actions/invoke` | `automations:run` | **Yes** |
| `send_command` | `POST /api/v1/actions/invoke` | `devices:command` | **Yes** |

`send_command` covers the curated core action registry: `tap {x,y}`, `swipe {direction}`,
`type_text {text}`, `press_key {key}`, `open_app {package}`, `uninstall_app {package}`,
`adb_shell {command}`, `reboot_device {}`. (`GET /api/v1/actions` lists the same registry with
full JSON schemas.) Extension-contributed tools are deliberately not invocable here — they stay
inside in-app agent conversations where their consent story lives.

## The safety story

- **Writes wait for a human.** A gated call blocks — possibly for minutes — until someone
  approves the pending action in the DeviceKit UI or the gate times out. Model-facing tool
  descriptions say so explicitly, so a well-behaved client won't treat the wait as a failure.
- **`DENIED` is an answer, not an error.** The invoke response is
  `{"device_id", "action", "result", "status"}`; `status: "denied"` with a `result` starting
  with `DENIED` means the approval was declined, timed out, or the device is in **observe**
  mode (read-only — writes are always refused).
- **Scopes bound the blast radius.** A key without `devices:command` cannot even *queue* a
  device write; the backend answers 403 and the tool relays it as an `ERROR 403: ...` string.
- **Autonomy is opt-in twice.** Auto-approval requires both the key's exact `mcp:autonomous`
  scope *and* the device being in autonomous mode — and it lands in the audit trail either way.
