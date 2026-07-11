> **Historical design doc — superseded.** This is the original Phase-16 design. For how the AI
> layer actually works today (the confirmation gate, session modes, NL automation, self-healing,
> per-device models), read **[docs/ai-agent.md](docs/ai-agent.md)**. This file is kept for design
> history; where it disagrees with the shipped system, the shipped system is right.

# Phase 16: Prompture Integration — Technical Design

## Overview

Replace the direct Anthropic/OpenAI API calls in `AgentMixin` with [Prompture](https://pypi.org/project/prompture/), giving every device a persistent conversational agent with personality, memory, tool use, structured output, and multi-provider support.

---

## What Changes

### Current Architecture (agent.py)

```
Screenshot (base64) -> _ask_anthropic() / _ask_openai() -> raw JSON text -> extract_json_from_text() -> execute action
```

- Stateless: no memory between cycles
- Single provider per deployment (AI_PROVIDER env var)
- Raw JSON parsing with regex fallback
- No token/cost tracking
- Profile injected as string interpolation in system prompt

### New Architecture (with Prompture)

```
Screenshot (base64) -> Conversation.ask() -> Pydantic DeviceAction model -> execute action
                            |
                            ├── ToolRegistry (device actions callable by LLM)
                            ├── Message history (conversation memory)
                            ├── UsageSession (token + cost tracking)
                            └── DriverCallbacks (observability hooks)
```

- Stateful: full conversation history per device
- Per-device model selection (Claude for device A, GPT-4 for device B, Ollama for device C)
- Validated structured output via Pydantic
- Token counting and cost tracking per device
- Tool use: LLM directly calls device actions in multi-step chains

---

## Dependency

Add to `backend/requirements.txt`:

```
prompture>=0.0.36
```

Prompture pulls in `anthropic`, `openai`, `google-generativeai`, `groq`, `httpx`, `pydantic`, and the rest. The existing `anthropic>=0.40.0` line can be removed since Prompture manages it.

---

## New File: `backend/devicekit/mixins/prompture_agent.py`

This mixin replaces `AgentMixin` with a Prompture-backed implementation.

### 1. Pydantic Action Model

Replace raw JSON parsing with a validated model:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class DeviceAction(BaseModel):
    """Structured action the AI agent wants to execute on the device."""
    action: Literal["tap", "swipe", "type", "press", "open_app", "wait", "done"]
    x: Optional[int] = None
    y: Optional[int] = None
    direction: Optional[Literal["up", "down", "left", "right"]] = None
    text: Optional[str] = None
    key: Optional[Literal["home", "back", "enter", "recent"]] = None
    package: Optional[str] = None
    description: str = Field(description="Brief explanation of why this action is taken")
    wait_seconds: float = Field(default=2.0, ge=0, le=30)
```

This eliminates `extract_json_from_text()` — Prompture validates the schema automatically.

### 2. Tool Registry for Device Actions

Instead of the LLM returning JSON that we parse and execute, register device actions as callable tools. The LLM invokes them directly in a reasoning loop:

```python
from prompture import ToolRegistry

def build_device_tools(mixin, device_id) -> ToolRegistry:
    """Create tool registry with device actions bound to a specific device."""
    registry = ToolRegistry()

    @registry.tool
    def tap(x: int, y: int) -> str:
        """Tap at screen coordinates (x, y)."""
        mixin.click(x, y, device_id)
        return f"Tapped at ({x}, {y})"

    @registry.tool
    def swipe(direction: str) -> str:
        """Swipe the screen. Direction: up, down, left, right."""
        d = mixin.get_device(device_id)
        info = d.info
        w = info.get("displayWidth", 1080)
        h = info.get("displayHeight", 1920)
        cx, cy = w // 2, h // 2
        swipe_map = {
            "up": (cx, h * 3 // 4, cx, h // 4),
            "down": (cx, h // 4, cx, h * 3 // 4),
            "left": (w * 3 // 4, cy, w // 4, cy),
            "right": (w // 4, cy, w * 3 // 4, cy),
        }
        coords = swipe_map.get(direction, swipe_map["up"])
        d.swipe(*coords, duration=0.5)
        return f"Swiped {direction}"

    @registry.tool
    def type_text(text: str) -> str:
        """Type text into the currently focused input field."""
        d = mixin.get_device(device_id)
        d.send_keys(text)
        return f"Typed: {text}"

    @registry.tool
    def press_key(key: str) -> str:
        """Press a device key: home, back, enter, recent."""
        mixin.press_action(key, device_id)
        return f"Pressed {key}"

    @registry.tool
    def open_app(package: str) -> str:
        """Open an app by its package name."""
        d = mixin.get_device(device_id)
        d.app_start(package)
        return f"Opened {package}"

    @registry.tool
    def describe_screen() -> str:
        """Take a screenshot and return a description of what is visible."""
        # In practice this sends a screenshot to the vision model
        # for now returns a placeholder — the main loop handles screenshots
        return "Screenshot captured for analysis"

    return registry
```

With tool use, the LLM can chain actions autonomously. Instead of one-action-per-cycle, a single `conv.ask("Open Instagram and like the first post")` can trigger: `open_app` -> `tap` -> `swipe` -> `tap` -> `done`, all in one turn with `max_tool_rounds=10`.

### 3. Per-Device Conversation with Personality

```python
from prompture import Conversation, DriverCallbacks, UsageSession

class DeviceConversation:
    """Wraps a Prompture Conversation for a specific device + profile."""

    def __init__(self, device_id: str, profile: dict, model_name: str,
                 tools: ToolRegistry, callbacks: DriverCallbacks = None):
        self.device_id = device_id
        self.profile = profile
        self.model_name = model_name
        self.session = UsageSession()

        if callbacks is None:
            callbacks = DriverCallbacks(
                on_response=self.session.record,
                on_error=self.session.record_error,
            )

        self.conversation = Conversation(
            model_name=model_name,
            system_prompt=self._build_system_prompt(profile),
            tools=tools,
            max_tool_rounds=10,
            callbacks=callbacks,
        )

    def _build_system_prompt(self, profile: dict) -> str:
        persona = profile.get("personality", "a helpful assistant")
        niche = profile.get("niche", "general")
        interests = ", ".join(profile.get("interests", []))
        behavior = profile.get("behavior_patterns", {})
        scroll_speed = behavior.get("scroll_speed", "medium")

        return (
            f"You are an AI agent controlling an Android phone.\n\n"
            f"## Your Identity\n"
            f"- Personality: {persona}\n"
            f"- Niche: {niche}\n"
            f"- Interests: {interests}\n"
            f"- Browsing style: {scroll_speed} scrolling\n\n"
            f"## Capabilities\n"
            f"You have tools to interact with the phone: tap, swipe, type_text, "
            f"press_key, open_app, and describe_screen.\n"
            f"Use these tools to accomplish tasks or browse naturally according to "
            f"your personality.\n\n"
            f"## Rules\n"
            f"- Always explain what you see and why you are taking an action.\n"
            f"- If a task is complete, say so clearly.\n"
            f"- If you are browsing autonomously, engage with content related to "
            f"your interests.\n"
            f"- Be patient — wait for screens to load before acting.\n"
        )

    @property
    def usage(self) -> dict:
        return self.session.summary()

    @property
    def history(self) -> list:
        return self.conversation.messages

    def clear(self):
        self.conversation.clear()

    def ask(self, message: str) -> str:
        return self.conversation.ask(message)

    def ask_stream(self, message: str):
        return self.conversation.ask_stream(message)
```

### 4. The New Mixin

```python
import logging
import threading
import time
from prompture import Conversation, ToolRegistry, DriverCallbacks, UsageSession

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude/claude-sonnet-4-20250514"


class PromptureAgentMixin:
    """AI agent backed by Prompture: conversations, tool use, memory, multi-provider."""

    _agent_conversations = {}   # device_id -> DeviceConversation
    _agent_states = {}
    _agent_threads = {}
    _agent_stop_events = {}
    _command_queues = {}
    _agent_logs = {}

    # ------------------------------------------------------------------
    # Public API (same interface as AgentMixin)
    # ------------------------------------------------------------------
    def get_agent_status(self, device_id):
        state = self._agent_states.get(device_id, {
            "status": "stopped",
            "current_action": None,
            "cycle_count": 0,
        })
        # Attach usage data if conversation exists
        conv = self._agent_conversations.get(device_id)
        if conv:
            state["usage"] = conv.usage
        return state

    def start_agent(self, device_id, profile, model_name=None):
        if device_id in self._agent_threads and self._agent_threads[device_id].is_alive():
            return {"error": "Agent already running"}

        model = model_name or profile.get("model_name") or DEFAULT_MODEL

        # Build tool registry for this device
        tools = build_device_tools(self, device_id)

        # Create or reuse conversation (preserves memory across restarts)
        if device_id not in self._agent_conversations:
            self._agent_conversations[device_id] = DeviceConversation(
                device_id=device_id,
                profile=profile,
                model_name=model,
                tools=tools,
            )

        self._agent_states[device_id] = {
            "status": "autonomous",
            "current_action": "Starting...",
            "cycle_count": 0,
        }
        self._command_queues.setdefault(device_id, [])
        self._agent_logs.setdefault(device_id, [])

        stop_event = threading.Event()
        self._agent_stop_events[device_id] = stop_event

        thread = threading.Thread(
            target=self._prompture_agent_loop,
            args=(device_id, profile, stop_event),
            daemon=True,
        )
        self._agent_threads[device_id] = thread
        thread.start()
        logger.info(f"Prompture agent started for {device_id} (model={model})")
        return self._agent_states[device_id]

    def stop_agent(self, device_id):
        event = self._agent_stop_events.get(device_id)
        if event:
            event.set()
        self._agent_states[device_id] = {
            "status": "stopped",
            "current_action": None,
            "cycle_count": self._agent_states.get(device_id, {}).get("cycle_count", 0),
        }
        self._agent_stop_events.pop(device_id, None)
        self._agent_threads.pop(device_id, None)
        # NOTE: conversation is NOT deleted — memory persists
        logger.info(f"Agent stopped for {device_id}")
        return self._agent_states[device_id]

    def get_conversation_history(self, device_id):
        conv = self._agent_conversations.get(device_id)
        return conv.history if conv else []

    def clear_conversation(self, device_id):
        conv = self._agent_conversations.get(device_id)
        if conv:
            conv.clear()
        return {"cleared": True}

    def get_agent_usage(self, device_id):
        conv = self._agent_conversations.get(device_id)
        return conv.usage if conv else {}

    # enqueue_command, get_command_queue, get_agent_logs — same as AgentMixin
    def enqueue_command(self, device_id, command_text, priority="normal"):
        self._command_queues.setdefault(device_id, [])
        cmd = {
            "command": command_text,
            "priority": priority,
            "status": "queued",
            "queued_at": time.time(),
        }
        if priority == "urgent":
            self._command_queues[device_id].insert(0, cmd)
        else:
            self._command_queues[device_id].append(cmd)
        return cmd

    def get_command_queue(self, device_id):
        return list(self._command_queues.get(device_id, []))

    def get_agent_logs(self, device_id, limit=50):
        logs = self._agent_logs.get(device_id, [])
        return logs[-limit:]

    # ------------------------------------------------------------------
    # Agent loop (Prompture-backed)
    # ------------------------------------------------------------------
    def _prompture_agent_loop(self, device_id, profile, stop_event):
        conv = self._agent_conversations[device_id]
        cycle = 0

        while not stop_event.is_set():
            try:
                # Check command queue first
                queue = self._command_queues.get(device_id, [])
                if queue:
                    cmd = queue.pop(0)
                    self._agent_states[device_id]["status"] = "executing_command"
                    self._agent_states[device_id]["current_action"] = f"Command: {cmd['command']}"
                    self._log_action(device_id, "command_start", cmd["command"])

                    # Prompture handles multi-step tool use automatically
                    response = conv.ask(
                        f"TASK: {cmd['command']}\n"
                        f"Complete this task using your tools. Explain what you do at each step."
                    )
                    self._log_action(device_id, "command_done", response[:200])
                    self._agent_states[device_id]["status"] = "autonomous"
                    continue

                # Autonomous cycle
                cycle += 1
                self._agent_states[device_id]["cycle_count"] = cycle

                screenshot_b64 = self._take_screenshot_b64(device_id)
                if not screenshot_b64:
                    self._agent_states[device_id]["current_action"] = "Screenshot failed, retrying..."
                    stop_event.wait(3)
                    continue

                # Send screenshot context + ask for natural browsing
                response = conv.ask(
                    f"Here is the current screen state (screenshot available). "
                    f"What do you see and what would you like to do next? "
                    f"Use your tools to interact with the phone."
                )

                desc = response[:200] if response else "No response"
                self._agent_states[device_id]["current_action"] = desc
                self._log_action(device_id, "autonomous", desc)

                stop_event.wait(2)

            except Exception as e:
                logger.error(f"Prompture agent loop error for {device_id}: {e}")
                self._log_action(device_id, "error", str(e))
                stop_event.wait(5)

        self._agent_states[device_id]["status"] = "stopped"
        self._agent_states[device_id]["current_action"] = None

    def _log_action(self, device_id, action, description):
        self._agent_logs.setdefault(device_id, [])
        entry = {
            "action": action,
            "description": description,
            "timestamp": time.time(),
        }
        self._agent_logs[device_id].append(entry)
        if len(self._agent_logs[device_id]) > 200:
            self._agent_logs[device_id] = self._agent_logs[device_id][-200:]
```

---

## Profile Changes

Extend the profile schema to include model selection:

```python
# In profile.py — add to create_profile defaults:
profile = {
    # ... existing fields ...
    "model_name": "claude/claude-sonnet-4-20250514",  # NEW: Prompture model string
}
```

The `model_name` field uses Prompture's `"provider/model"` format. Examples:

| Provider | model_name value |
|---|---|
| Claude | `claude/claude-sonnet-4-20250514` |
| OpenAI | `openai/gpt-4o` |
| Groq | `groq/llama-3.1-70b-versatile` |
| Ollama (local) | `ollama/llama3.1:8b` |
| Google | `google/gemini-2.0-flash` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4` |
| LM Studio | `lmstudio/local-model` |

This lets each device run a different model. A test device might use `ollama/llama3.1:8b` (free, local), while a production device uses `claude/claude-sonnet-4-20250514`.

---

## API Endpoints to Add

In `api_app.py`, add these routes:

```python
# GET /devices/<device_id>/conversation/history
# Returns the full conversation message history for the device agent.
# Response: {"messages": [...], "turn_count": int}

# DELETE /devices/<device_id>/conversation
# Clears conversation history (resets memory but keeps personality).
# Response: {"cleared": true}

# GET /devices/<device_id>/agent/usage
# Returns token counts and cost for this device's agent.
# Response: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int,
#            "total_cost": float, "call_count": int, "errors": int}

# PATCH /devices/<device_id>/agent/model
# Switch the LLM model for a device's agent.
# Body: {"model_name": "openai/gpt-4o"}
# Response: {"model_name": "openai/gpt-4o", "restarted": bool}
```

---

## Frontend Changes

### Profile Editor (`ProfileEditor.jsx`)

Add a model selector dropdown to the profile form:

```
Model: [claude/claude-sonnet-4-20250514 ▼]
        openai/gpt-4o
        groq/llama-3.1-70b-versatile
        ollama/llama3.1:8b
        google/gemini-2.0-flash
        (custom input)
```

### Node Detail (`NodeDetail.jsx`)

Add new sections to the device detail view:

- **Agent Usage Panel**: shows tokens used, cost, call count
- **Conversation History**: scrollable message log (user/assistant turns)
- **Clear Conversation** button
- **Model Badge**: shows which LLM is powering this device

### Dashboard (`Dashboard.jsx`)

- **Fleet AI Cost**: total cost across all active agents
- **Per-device token usage**: in the device card

---

## Migration Path

### Step 1: Add Dependency

```diff
# backend/requirements.txt
+ prompture>=0.0.36
- anthropic>=0.40.0  # Now managed by prompture
```

### Step 2: Create the New Mixin

Add `backend/devicekit/mixins/prompture_agent.py` with the `PromptureAgentMixin` class above.

### Step 3: Swap in client.py

```diff
# backend/devicekit/client.py
- from .mixins.agent import AgentMixin
+ from .mixins.prompture_agent import PromptureAgentMixin

class Client(
    AdbMixin,
    Uiautomator2Mixin,
    CdpMixin,
    DynamodbMixin,
    AwsStorageMixin,
    AutomationMixin,
    ProfileMixin,
-   AgentMixin,
+   PromptureAgentMixin,
    ApiAppMixin,
    QueueMixin,
    AlertMixin,
    ActivityMixin,
    ToolsMixin,
):
    pass
```

The public API is identical (`start_agent`, `stop_agent`, `enqueue_command`, `get_agent_status`, `get_agent_logs`) so no other backend code changes are needed for basic operation. The new methods (`get_conversation_history`, `clear_conversation`, `get_agent_usage`) are additive.

### Step 4: Extend Profile Schema

Add `model_name` to profile creation and the frontend form.

### Step 5: Add API Routes

Wire the new conversation/usage endpoints in `api_app.py`.

### Step 6: Frontend Updates

Add usage display, model selector, and conversation history views.

---

## What This Enables

### Before (current AgentMixin)

- Stateless: each screenshot-action cycle is independent
- Single provider: locked to `AI_PROVIDER` env var (anthropic or openai)
- Raw JSON: manual parsing with regex fallback
- No tracking: no idea how many tokens or dollars each device consumes
- No memory: device has no awareness of what it did 5 seconds ago

### After (PromptureAgentMixin)

- **Memory**: device remembers its entire interaction history. "Open the app I was using earlier" works.
- **Multi-provider**: each device can run a different model. Mix Claude, GPT-4, Groq, Ollama.
- **Tool use**: LLM calls device actions directly in multi-step chains. One `conv.ask()` call can trigger 5 actions in sequence without round-tripping through the loop.
- **Structured output**: validated Pydantic models instead of regex JSON extraction.
- **Cost tracking**: per-device token counts and dollar costs visible on the dashboard.
- **Streaming**: real-time "thinking" feedback from the AI as it reasons through actions.
- **Observability**: callbacks on every request/response for logging, alerting, debugging.
- **Caching**: identical prompts can be cached to avoid redundant API calls.
- **Personality persistence**: conversation history survives agent stop/start. The device "remembers" across sessions.

---

## Configuration

Environment variables (in `.env`):

```bash
# Default model for devices without a profile model_name
PROMPTURE_DEFAULT_MODEL=claude/claude-sonnet-4-20250514

# Provider API keys (Prompture loads from env automatically)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=AI...

# Optional: Ollama for local/free models
OLLAMA_HOST=http://localhost:11434

# Optional: Prompture caching
PROMPTURE_CACHE_ENABLED=true
PROMPTURE_CACHE_BACKEND=sqlite
PROMPTURE_CACHE_TTL=3600
```

---

## Testing

### Unit Tests

Test the new mixin without live LLM calls:

```python
# tests/test_prompture_agent.py

def test_build_device_tools():
    """Tool registry creates correct function schemas."""
    # Mock mixin with click/press_action/get_device methods
    tools = build_device_tools(mock_mixin, "device-123")
    assert "tap" in [t.name for t in tools.definitions]
    assert "swipe" in [t.name for t in tools.definitions]

def test_device_conversation_system_prompt():
    """System prompt incorporates profile fields."""
    conv = DeviceConversation(
        device_id="test",
        profile={"personality": "curious explorer", "niche": "photography", "interests": ["nature", "portraits"]},
        model_name="ollama/llama3.1:8b",
        tools=ToolRegistry(),
    )
    prompt = conv.conversation._system_prompt
    assert "curious explorer" in prompt
    assert "photography" in prompt
    assert "nature" in prompt

def test_start_stop_preserves_memory():
    """Stopping and restarting agent keeps conversation history."""
    mixin = MockPromptureAgentMixin()
    mixin.start_agent("dev1", profile, model_name="ollama/llama3.1:8b")
    # ... interact ...
    mixin.stop_agent("dev1")
    assert "dev1" in mixin._agent_conversations  # NOT deleted
    mixin.start_agent("dev1", profile)
    assert len(mixin._agent_conversations["dev1"].history) > 0
```

### Integration Tests

Test with a real Ollama instance (free, local):

```python
@pytest.mark.integration
def test_prompture_conversation_with_ollama():
    """Full conversation with local Ollama model."""
    from prompture import Conversation, ToolRegistry

    registry = ToolRegistry()
    @registry.tool
    def mock_tap(x: int, y: int) -> str:
        return f"Tapped ({x}, {y})"

    conv = Conversation(
        model_name="ollama/llama3.1:8b",
        system_prompt="You control an Android phone. Use tools to interact.",
        tools=registry,
    )
    response = conv.ask("Tap the center of the screen at 540, 960")
    assert "tapped" in response.lower() or "540" in response
```

---

## Sequence Diagrams

### Autonomous Browsing Cycle

```
Frontend          Backend (PromptureAgentMixin)        Prompture             LLM Provider
   │                       │                              │                      │
   │  POST /agent/start    │                              │                      │
   ├──────────────────────►│                              │                      │
   │                       │ DeviceConversation(profile)  │                      │
   │                       ├─────────────────────────────►│                      │
   │                       │                              │                      │
   │                       │ ── loop ──                   │                      │
   │                       │ take screenshot              │                      │
   │                       │ conv.ask("What do you see?") │                      │
   │                       ├─────────────────────────────►│                      │
   │                       │                              │  messages + tools    │
   │                       │                              ├─────────────────────►│
   │                       │                              │  tool_call: tap()    │
   │                       │                              │◄─────────────────────┤
   │                       │                              │  execute tap         │
   │                       │  click(x, y, device_id)      │                      │
   │                       │◄─────────────────────────────┤                      │
   │                       │                              │  tool_result         │
   │                       │                              ├─────────────────────►│
   │                       │                              │  tool_call: swipe()  │
   │                       │                              │◄─────────────────────┤
   │                       │  swipe on device             │                      │
   │                       │◄─────────────────────────────┤                      │
   │                       │                              │  final text response │
   │                       │                              │◄─────────────────────┤
   │                       │  log action + update state   │                      │
   │                       │  wait 2s, next cycle         │                      │
   │                       │                              │                      │
   │  GET /agent/status    │                              │                      │
   ├──────────────────────►│                              │                      │
   │  {status, usage, ...} │                              │                      │
   │◄──────────────────────┤                              │                      │
```

### Command Execution

```
User types command in frontend
   │
   │  POST /agent/command {command: "Open Chrome and go to google.com"}
   ├──────────────────────────────────────────────────────────────────►  Backend
   │                                                                      │
   │                            conv.ask("TASK: Open Chrome and ...")      │
   │                                        │                             │
   │                                        ▼                             │
   │                            LLM reasons: "I need to open Chrome"      │
   │                            LLM calls: open_app("com.android.chrome") │
   │                            Tool executes on device                   │
   │                            LLM sees result, calls: tap(url_bar)      │
   │                            LLM calls: type_text("google.com")        │
   │                            LLM calls: press_key("enter")             │
   │                            LLM responds: "Done. Chrome is showing    │
   │                                           google.com"                │
   │                                                                      │
   │  GET /agent/logs                                                     │
   ├─────────────────────────────────────────────────────────────────────►│
   │  [{action: "command_done", description: "Done. Chrome is..."}]       │
   │◄─────────────────────────────────────────────────────────────────────┤
```

---

## File Checklist

| File | Action | Description |
|---|---|---|
| `backend/requirements.txt` | Modify | Add `prompture>=0.0.36`, remove `anthropic>=0.40.0` |
| `backend/devicekit/mixins/prompture_agent.py` | Create | New mixin with Prompture Conversation + ToolRegistry |
| `backend/devicekit/client.py` | Modify | Swap `AgentMixin` for `PromptureAgentMixin` |
| `backend/devicekit/mixins/profile.py` | Modify | Add `model_name` field to profile schema |
| `backend/devicekit/mixins/api_app.py` | Modify | Add conversation history, usage, model switch endpoints |
| `backend/config.py` | Modify | Add `PROMPTURE_DEFAULT_MODEL` config |
| `frontend/src/api.js` | Modify | Add API methods for new endpoints |
| `frontend/src/views/NodeDetail.jsx` | Modify | Add usage panel, conversation history section |
| `frontend/src/views/ProfileEditor.jsx` | Modify | Add model selector dropdown |
| `frontend/src/views/Dashboard.jsx` | Modify | Add fleet AI cost summary |
| `tests/test_prompture_agent.py` | Create | Unit + integration tests |
| `.env.example` | Modify | Add Prompture config vars |
