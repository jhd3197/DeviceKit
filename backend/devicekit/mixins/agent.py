import os
import time
import base64
import logging
import threading

logger = logging.getLogger(__name__)

AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")
MAX_COMMAND_STEPS = 20


class AgentMixin:
    """AI agent system: screenshot -> vision AI -> execute action -> repeat."""

    _agent_states = {}
    _agent_threads = {}
    _agent_stop_events = {}
    _command_queues = {}
    _agent_logs = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_agent_status(self, device_id):
        return self._agent_states.get(device_id, {
            "status": "stopped",
            "current_action": None,
            "cycle_count": 0,
        })

    def get_all_agent_status(self):
        result = {}
        for device_id in list(self._agent_states):
            result[device_id] = self._agent_states[device_id]
        return result

    def start_agent(self, device_id, profile):
        if device_id in self._agent_threads and self._agent_threads[device_id].is_alive():
            return {"error": "Agent already running"}

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
            target=self._agent_loop,
            args=(device_id, profile, stop_event),
            daemon=True,
        )
        self._agent_threads[device_id] = thread
        thread.start()
        logger.info(f"Agent started for {device_id} with profile '{profile.get('name')}'")
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
    # Agent loop
    # ------------------------------------------------------------------
    def _agent_loop(self, device_id, profile, stop_event):
        cycle = 0
        while not stop_event.is_set():
            try:
                # Check command queue
                queue = self._command_queues.get(device_id, [])
                if queue:
                    cmd = queue.pop(0)
                    self._agent_states[device_id]["status"] = "executing_command"
                    self._agent_states[device_id]["current_action"] = f"Command: {cmd['command']}"
                    self._log_action(device_id, "command_start", cmd["command"])
                    self._execute_ai_command(device_id, profile, cmd["command"], stop_event)
                    self._agent_states[device_id]["status"] = "autonomous"
                    self._log_action(device_id, "command_done", cmd["command"])
                    continue

                # Autonomous cycle
                cycle += 1
                self._agent_states[device_id]["cycle_count"] = cycle

                screenshot_b64 = self._take_screenshot_b64(device_id)
                if not screenshot_b64:
                    self._agent_states[device_id]["current_action"] = "Screenshot failed, retrying..."
                    stop_event.wait(3)
                    continue

                action = self._ask_ai_for_action(
                    screenshot_b64, profile, mode="autonomous", task=None
                )
                if not action or action.get("action") == "wait":
                    wait_secs = (action or {}).get("wait_seconds", 3)
                    desc = (action or {}).get("description", "Waiting")
                    self._agent_states[device_id]["current_action"] = desc
                    self._log_action(device_id, "wait", desc)
                    stop_event.wait(min(wait_secs, 10))
                    continue

                desc = action.get("description", str(action.get("action")))
                self._agent_states[device_id]["current_action"] = desc
                self._log_action(device_id, action.get("action", "unknown"), desc)
                self._execute_ai_action(device_id, action)

                wait_secs = action.get("wait_seconds", 2)
                stop_event.wait(min(wait_secs, 10))

            except Exception as e:
                logger.error(f"Agent loop error for {device_id}: {e}")
                self._log_action(device_id, "error", str(e))
                stop_event.wait(5)

        self._agent_states[device_id]["status"] = "stopped"
        self._agent_states[device_id]["current_action"] = None

    def _execute_ai_command(self, device_id, profile, command_text, stop_event):
        for step in range(MAX_COMMAND_STEPS):
            if stop_event.is_set():
                return

            screenshot_b64 = self._take_screenshot_b64(device_id)
            if not screenshot_b64:
                time.sleep(1)
                continue

            action = self._ask_ai_for_action(
                screenshot_b64, profile, mode="command", task=command_text
            )
            if not action or action.get("action") == "done":
                self._log_action(device_id, "done", f"Completed: {command_text}")
                return

            desc = action.get("description", str(action.get("action")))
            self._agent_states[device_id]["current_action"] = f"[Cmd] {desc}"
            self._log_action(device_id, action.get("action", "unknown"), f"[Cmd] {desc}")
            self._execute_ai_action(device_id, action)

            wait_secs = action.get("wait_seconds", 1.5)
            time.sleep(min(wait_secs, 10))

        self._log_action(device_id, "timeout", f"Command exceeded {MAX_COMMAND_STEPS} steps: {command_text}")

    # ------------------------------------------------------------------
    # AI integration
    # ------------------------------------------------------------------
    def _take_screenshot_b64(self, device_id):
        try:
            data = self.take_screenshot(device_id)
            if data:
                return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.error(f"Screenshot for agent failed on {device_id}: {e}")
        return None

    def _ask_ai_for_action(self, screenshot_b64, profile, mode="autonomous", task=None):
        persona = profile.get("personality", "a normal user")
        niche = profile.get("niche", "general")
        interests = ", ".join(profile.get("interests", []))

        system_prompt = (
            f"You are controlling an Android phone. You are acting as: {persona}.\n"
            f"Niche: {niche}. Interests: {interests}.\n\n"
            f"Available actions (respond with JSON):\n"
            f'  {{"action": "tap", "x": <int>, "y": <int>, "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "swipe", "direction": "up|down|left|right", "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "type", "text": "...", "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "press", "key": "home|back|enter|recent", "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "open_app", "package": "...", "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "wait", "description": "...", "wait_seconds": <float>}}\n'
            f'  {{"action": "done", "description": "..."}}\n\n'
        )

        if mode == "command":
            system_prompt += (
                f"TASK: {task}\n"
                f"Complete this task step by step. Return 'done' when finished.\n"
            )
        else:
            system_prompt += (
                "Browse and interact naturally as this persona would. "
                "Engage with content related to your interests.\n"
            )

        system_prompt += "Respond ONLY with a single JSON action object."

        try:
            if AI_PROVIDER == "openai":
                return self._ask_openai(system_prompt, screenshot_b64)
            else:
                return self._ask_anthropic(system_prompt, screenshot_b64)
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            return {"action": "wait", "description": f"AI error: {e}", "wait_seconds": 5}

    def _ask_anthropic(self, system_prompt, screenshot_b64):
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": "What action should I take next?"},
                ],
            }],
        )
        text = response.content[0].text
        return self.extract_json_from_text(text)

    def _ask_openai(self, system_prompt, screenshot_b64):
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=300,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                            },
                        },
                        {"type": "text", "text": "What action should I take next?"},
                    ],
                },
            ],
        )
        text = response.choices[0].message.content
        return self.extract_json_from_text(text)

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------
    def _execute_ai_action(self, device_id, action):
        act = action.get("action")
        try:
            if act == "tap":
                x = int(action.get("x", 0))
                y = int(action.get("y", 0))
                self.click(x, y, device_id)
            elif act == "swipe":
                direction = action.get("direction", "up")
                d = self.get_device(device_id)
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
            elif act == "type":
                text = action.get("text", "")
                d = self.get_device(device_id)
                d.send_keys(text)
            elif act == "press":
                key = action.get("key", "home")
                self.press_action(key, device_id)
            elif act == "open_app":
                package = action.get("package", "")
                d = self.get_device(device_id)
                d.app_start(package)
            elif act == "done":
                pass
            else:
                logger.warning(f"Unknown AI action: {act}")
        except Exception as e:
            logger.error(f"Failed to execute AI action {act} on {device_id}: {e}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
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
