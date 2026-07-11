import base64
import logging
import time
import threading
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_COMMAND_STEPS = 20


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


def build_device_tools(mixin, device_id, mode="supervised"):
    """Create a tool registry bound to a specific device, annotated for the safety gate.

    Every tool carries ``metadata`` (``is_write`` + ``category`` + a human ``label``).
    Read tools run unmediated. Write tools are wrapped so their execution routes through
    ``mixin.gate_tool_call`` (the ConfirmationGate). In ``observe`` mode write tools are
    filtered out of the registry entirely — the model never even sees them (plan 13).
    """
    from prompture import ToolRegistry

    registry = ToolRegistry()

    def add(fn, *, is_write, category, label, name=None):
        # observe = read-only: hide write tools from the model, don't merely block them.
        if is_write and mode == "observe":
            return
        meta = {"is_write": is_write, "category": category, "label": label}
        tool_name = name or fn.__name__
        td = registry.register(fn, name=tool_name, metadata=meta)
        if is_write:
            _gate_write_tool(mixin, device_id, td, meta, source="core")

    # ---------------------------------------------------------------- read tools (no gate)
    def get_battery() -> str:
        """Report the device battery level and charging state."""
        return str(mixin.get_device_battery(device=device_id))

    def device_properties() -> str:
        """Return device model, resolution, and Android build info."""
        return str(mixin.get_device(device_id).info)

    def get_ui_hierarchy() -> str:
        """Dump the current on-screen UI element tree (XML)."""
        return (mixin.get_device(device_id).dump_hierarchy() or "")[:8000]

    def list_installed_apps() -> str:
        """List third-party app package names installed on the device."""
        return str(mixin.run_adb_command(["shell", "pm", "list", "packages", "-3"],
                                         device=device_id))

    add(get_battery, is_write=False, category="read", label="Get battery")
    add(device_properties, is_write=False, category="read", label="Device properties")
    add(get_ui_hierarchy, is_write=False, category="read", label="UI hierarchy")
    add(list_installed_apps, is_write=False, category="read", label="List apps")

    # -------------------------------------------------------------- write tools (gated)
    def tap(x: int, y: int) -> str:
        """Tap at screen coordinates (x, y)."""
        mixin.click(x, y, device_id)
        return f"Tapped at ({x}, {y})"

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

    def type_text(text: str) -> str:
        """Type text into the currently focused input field."""
        d = mixin.get_device(device_id)
        d.send_keys(text)
        return f"Typed: {text}"

    def press_key(key: str) -> str:
        """Press a device key: home, back, enter, recent."""
        mixin.press_action(key, device_id)
        return f"Pressed {key}"

    def open_app(package: str) -> str:
        """Open an app by its package name."""
        d = mixin.get_device(device_id)
        d.app_start(package)
        return f"Opened {package}"

    def uninstall_app(package: str) -> str:
        """Uninstall an app by its package name."""
        out = mixin.run_adb_command(["uninstall", package], device=device_id)
        return f"Uninstalled {package}: {out}"

    def adb_shell(command: str) -> str:
        """Run an arbitrary adb shell command on the device."""
        return str(mixin.run_adb_command(["shell", command], device=device_id))

    def reboot_device() -> str:
        """Reboot the device."""
        mixin.reboot_device(device=device_id)
        return "Reboot requested"

    add(tap, is_write=True, category="input", label="Tap")
    add(swipe, is_write=True, category="input", label="Swipe")
    add(type_text, is_write=True, category="input", label="Type text")
    add(press_key, is_write=True, category="input", label="Press key")
    add(open_app, is_write=True, category="app", label="Open app")
    add(uninstall_app, is_write=True, category="app", label="Uninstall app")
    add(adb_shell, is_write=True, category="shell", label="adb shell")
    add(reboot_device, is_write=True, category="power", label="Reboot device")

    # Extension-contributed AI tools (plan 03), namespaced ``<slug>__<name>`` to satisfy
    # provider function-name limits. Only tools from active extensions are bound.
    _register_extension_ai_tools(mixin, registry, device_id, mode)

    return registry


def _gate_write_tool(mixin, device_id, td, meta, source, always_gate=False):
    """Replace a tool's callable with a gated wrapper. The JSON schema was already built
    from the real function at registration time, so the model still sees the true
    signature; only execution is mediated."""
    real_fn = td.function
    tool_name = td.name
    gate_meta = dict(meta)
    if always_gate:
        gate_meta["always_gate"] = True

    def gated(**kwargs):
        return mixin.gate_tool_call(device_id, tool_name, kwargs, gate_meta, source, real_fn)

    td.function = gated


def _bind_device_id(func, device_id):
    """If ``func`` declares a ``device_id`` parameter, return a wrapper that injects the
    current device and hides ``device_id`` from the tool schema; otherwise return ``func``
    unchanged."""
    import inspect
    import functools
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return func
    if "device_id" not in sig.parameters:
        return func

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        kwargs.setdefault("device_id", device_id)
        return func(*args, **kwargs)

    wrapper.__signature__ = sig.replace(
        parameters=[p for n, p in sig.parameters.items() if n != "device_id"])
    return wrapper


def _register_extension_ai_tools(mixin, registry, device_id, mode="supervised"):
    ext_tools = getattr(mixin, "_ext_ai_tools", None)
    if not ext_tools:
        return
    for slug, tools in list(ext_tools.items()):
        # Respect the status guard: skip tools from a disabled/errored extension.
        try:
            row = mixin.get_extension(slug)
            if not row or row.get("status") != "active":
                continue
        except Exception:
            pass
        for entry in tools:
            # Tuple is (name, func, description) or (name, func, description, is_write).
            name, func, description = entry[0], entry[1], entry[2]
            is_write = entry[3] if len(entry) > 3 else True
            # Extension write tools are always gated — third-party code never gets
            # autonomous hardware access — and are hidden in observe mode.
            if is_write and mode == "observe":
                continue
            tool_name = f"{slug.replace('-', '_')}__{name}"
            # Device-scoped tools: a tool that declares a ``device_id`` parameter is bound to
            # this conversation's device, and that parameter is hidden from the LLM-facing
            # schema (the model addresses "this device" implicitly). Fleet-level tools that
            # omit ``device_id`` are unaffected.
            bound = _bind_device_id(func, device_id)
            try:
                td = registry.register(bound, name=tool_name, description=description,
                                       metadata={"is_write": is_write, "category": "extension",
                                                 "label": f"{slug}: {name}"})
                if is_write:
                    _gate_write_tool(mixin, device_id, td,
                                     {"is_write": True, "category": "extension",
                                      "label": f"{slug}: {name}"},
                                     source=f"extension:{slug}", always_gate=True)
            except Exception as e:
                logger.warning(f"Failed to bind extension AI tool {tool_name}: {e}")


class DeviceConversation:
    """Wraps a Prompture Conversation for a specific device + profile."""

    def __init__(self, device_id, profile, model_name, tools, callbacks=None):
        from prompture import Conversation, DriverCallbacks, UsageSession

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

    def _build_system_prompt(self, profile):
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
            f"press_key, open_app.\n"
            f"Use these tools to accomplish tasks or browse naturally according to "
            f"your personality.\n\n"
            f"## Rules\n"
            f"- Always explain what you see and why you are taking an action.\n"
            f"- If a task is complete, say so clearly.\n"
            f"- If you are browsing autonomously, engage with content related to "
            f"your interests.\n"
            f"- Be patient -- wait for screens to load before acting.\n"
        )

    @property
    def usage(self):
        return self.session.summary()

    @property
    def history(self):
        return self.conversation.messages

    def clear(self):
        self.conversation.clear()

    def ask(self, message):
        return self.conversation.ask(message)

    def ask_stream(self, message):
        return self.conversation.ask_stream(message)


class PromptureAgentMixin:
    """AI agent backed by Prompture: conversations, tool use, memory, multi-provider."""

    _agent_conversations = {}   # device_id -> DeviceConversation
    _agent_states = {}
    _agent_threads = {}
    _agent_stop_events = {}
    _command_queues = {}
    _agent_logs = {}

    # ------------------------------------------------------------------
    # Public API (same interface as AgentMixin + new methods)
    # ------------------------------------------------------------------
    def get_agent_status(self, device_id):
        state = self._agent_states.get(device_id, {
            "status": "stopped",
            "current_action": None,
            "cycle_count": 0,
        })
        conv = self._agent_conversations.get(device_id)
        if conv:
            state["usage"] = conv.usage
            state["model_name"] = conv.model_name
        state["mode"] = self.get_agent_mode(device_id)
        state["pending_actions"] = self.list_pending_actions(device_id)
        return state

    def get_all_agent_status(self):
        result = {}
        for device_id in list(self._agent_states):
            result[device_id] = self.get_agent_status(device_id)
        return result

    def start_agent(self, device_id, profile, model_name=None):
        if device_id in self._agent_threads and self._agent_threads[device_id].is_alive():
            return {"error": "Agent already running"}

        # Effective default: explicit arg > profile > saved AI setting (falls back to
        # PROMPTURE_DEFAULT_MODEL when unset) — the Settings AI pane can now steer this
        # without a .env edit.
        model = model_name or profile.get("model_name") or self.ai_default_model()

        # Build tool registry for this device, filtered/gated for the session mode.
        mode = self.get_agent_mode(device_id)
        tools = build_device_tools(self, device_id, mode=mode)

        # Create or reuse conversation (preserves memory across restarts)
        if device_id not in self._agent_conversations:
            try:
                self._agent_conversations[device_id] = DeviceConversation(
                    device_id=device_id,
                    profile=profile,
                    model_name=model,
                    tools=tools,
                )
            except Exception as e:
                logger.error(f"Failed to create Prompture conversation for {device_id}: {e}")
                return {"error": f"Prompture initialization failed: {e}"}

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
        # NOTE: conversation is NOT deleted -- memory persists
        logger.info(f"Agent stopped for {device_id}")
        return self._agent_states[device_id]

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
        logger.info(f"Enqueued command for {device_id}: {command_text}")
        return cmd

    def get_command_queue(self, device_id):
        return list(self._command_queues.get(device_id, []))

    def get_agent_logs(self, device_id, limit=50):
        logs = self._agent_logs.get(device_id, [])
        return logs[-limit:]

    # ------------------------------------------------------------------
    # New Prompture-specific methods
    # ------------------------------------------------------------------
    def get_conversation_history(self, device_id):
        conv = self._agent_conversations.get(device_id)
        if not conv:
            return []
        messages = conv.history
        # Serialize messages to dicts for JSON response
        serialized = []
        for msg in messages:
            if isinstance(msg, dict):
                serialized.append(msg)
            elif hasattr(msg, "model_dump"):
                serialized.append(msg.model_dump())
            else:
                serialized.append({"role": "unknown", "content": str(msg)})
        return serialized

    def clear_conversation(self, device_id):
        conv = self._agent_conversations.get(device_id)
        if conv:
            conv.clear()
        return {"cleared": True}

    def get_agent_usage(self, device_id):
        conv = self._agent_conversations.get(device_id)
        if not conv:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "call_count": 0,
                "errors": 0,
            }
        return conv.usage

    def switch_agent_model(self, device_id, model_name):
        conv = self._agent_conversations.get(device_id)
        if conv:
            conv.model_name = model_name
            conv.conversation.model_name = model_name
        return {"model_name": model_name, "applied": conv is not None}

    # ------------------------------------------------------------------
    # Agent loop (Prompture-backed)
    # ------------------------------------------------------------------
    def _prompture_agent_loop(self, device_id, profile, stop_event):
        conv = self._agent_conversations.get(device_id)
        if not conv:
            logger.error(f"No conversation found for {device_id}")
            return

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

                    try:
                        response = conv.ask(
                            f"TASK: {cmd['command']}\n"
                            f"Complete this task using your tools. "
                            f"Explain what you do at each step."
                        )
                        self._log_action(device_id, "command_done", (response or "")[:200])
                    except Exception as e:
                        logger.error(f"Command execution error for {device_id}: {e}")
                        self._log_action(device_id, "error", f"Command failed: {e}")

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

                try:
                    response = conv.ask(
                        "Here is the current screen state. "
                        "What do you see and what would you like to do next? "
                        "Use your tools to interact with the phone."
                    )
                    desc = (response or "No response")[:200]
                    self._agent_states[device_id]["current_action"] = desc
                    self._log_action(device_id, "autonomous", desc)
                except Exception as e:
                    logger.error(f"Autonomous cycle error for {device_id}: {e}")
                    self._log_action(device_id, "error", str(e))

                stop_event.wait(2)

            except Exception as e:
                logger.error(f"Prompture agent loop error for {device_id}: {e}")
                self._log_action(device_id, "error", str(e))
                stop_event.wait(5)

        self._agent_states[device_id]["status"] = "stopped"
        self._agent_states[device_id]["current_action"] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _take_screenshot_b64(self, device_id):
        try:
            data = self.take_screenshot(device_id)
            if data:
                return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.error(f"Screenshot for agent failed on {device_id}: {e}")
        return None

    def _log_action(self, device_id, action, description):
        self._agent_logs.setdefault(device_id, [])
        entry = {
            "action": action,
            "description": description,
            "timestamp": time.time(),
        }
        self._agent_logs[device_id].append(entry)
        # Keep last 200 entries per device
        if len(self._agent_logs[device_id]) > 200:
            self._agent_logs[device_id] = self._agent_logs[device_id][-200:]
