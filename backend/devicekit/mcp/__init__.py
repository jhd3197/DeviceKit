"""The DeviceKit MCP server (plan 21, part 3).

A first-class Model Context Protocol server that exposes a *curated* slice of the scoped
``/api/v1`` HTTP surface as MCP tools, so any MCP client (Claude Code, Claude Desktop, a
custom agent) can read fleet state and — with the right scopes — drive devices.

The safety story, in three layers:

1. **Scopes decide what the key may even attempt.** The server authenticates every HTTP
   call with a ``dk_`` API key (``X-API-Key``); reads need ``devices:read`` /
   ``automations:read`` / ``metrics:read``, writes need ``devices:command`` /
   ``automations:run``. A read-only key makes the write tools return a clean 403 error
   string — nothing device-touching can happen.
2. **Every write flows through the plan-13 confirmation gate.** ``send_command`` and
   ``run_automation`` call ``POST /api/v1/actions/invoke``, which routes each write
   through the same pending-action → human-approval flow an in-app AI action gets. The
   HTTP call *blocks* until a human approves in the DeviceKit UI or the gate times out;
   a result starting with ``DENIED`` means declined, timed out, or observe mode.
3. **``mcp:autonomous`` is the explicit opt-in for auto-approval.** Without that exact
   scope (wildcards deliberately don't grant it) an external key is always-gated, even
   on a device whose agent mode is ``autonomous``. With it, the device's mode decides —
   and the auto-approval is audited like any other gate decision.

Run it with ``python -m devicekit.mcp`` (stdio, the default) or
``python -m devicekit.mcp --transport streamable-http`` (HTTP at ``/mcp``). Configuration
comes from ``DEVICEKIT_URL``, ``DEVICEKIT_API_KEY``, and ``DEVICEKIT_MCP_INVOKE_TIMEOUT``;
see ``docs/mcp-server.md`` for key minting and client wiring.
"""
