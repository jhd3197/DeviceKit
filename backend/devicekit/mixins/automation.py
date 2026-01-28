import uuid
import time
import logging
import threading

logger = logging.getLogger(__name__)

STEP_TYPES = {
    "tap": {
        "label": "Tap (x, y)",
        "category": "Interaction",
        "config": {
            "x": {"type": "number", "label": "X coordinate", "required": True},
            "y": {"type": "number", "label": "Y coordinate", "required": True},
        },
    },
    "tap_by_text": {
        "label": "Tap by Text",
        "category": "Interaction",
        "config": {
            "text": {"type": "text", "label": "Element text", "required": True},
        },
    },
    "tap_by_resource_id": {
        "label": "Tap by Resource ID",
        "category": "Interaction",
        "config": {
            "resource_id": {"type": "text", "label": "Resource ID", "required": True},
        },
    },
    "swipe": {
        "label": "Swipe",
        "category": "Interaction",
        "config": {
            "direction": {
                "type": "select",
                "label": "Direction",
                "required": True,
                "options": ["up", "down", "left", "right"],
            },
            "duration": {"type": "number", "label": "Duration (ms)", "required": False, "default": 500},
        },
    },
    "type_text": {
        "label": "Type Text",
        "category": "Interaction",
        "config": {
            "text": {"type": "text", "label": "Text to type", "required": True},
        },
    },
    "press_key": {
        "label": "Press Key",
        "category": "Interaction",
        "config": {
            "key": {
                "type": "select",
                "label": "Key",
                "required": True,
                "options": ["home", "back", "enter", "menu", "recent", "volume_up", "volume_down", "power"],
            },
        },
    },
    "open_app": {
        "label": "Open App",
        "category": "Apps",
        "config": {
            "package": {"type": "text", "label": "Package name", "required": True},
        },
    },
    "close_app": {
        "label": "Close App",
        "category": "Apps",
        "config": {
            "package": {"type": "text", "label": "Package name", "required": True},
        },
    },
    "open_url": {
        "label": "Open URL",
        "category": "Apps",
        "config": {
            "url": {"type": "text", "label": "URL", "required": True},
        },
    },
    "wait": {
        "label": "Wait",
        "category": "Timing",
        "config": {
            "delay": {"type": "number", "label": "Delay (ms)", "required": True, "default": 1000},
        },
    },
    "wait_for_element": {
        "label": "Wait for Element",
        "category": "Timing",
        "config": {
            "by": {
                "type": "select",
                "label": "Find by",
                "required": True,
                "options": ["text", "resource_id"],
            },
            "value": {"type": "text", "label": "Value", "required": True},
            "timeout": {"type": "number", "label": "Timeout (ms)", "required": False, "default": 10000},
        },
    },
    "screenshot": {
        "label": "Screenshot",
        "category": "Debug",
        "config": {},
    },
    "assert_element": {
        "label": "Assert Element",
        "category": "Debug",
        "config": {
            "by": {
                "type": "select",
                "label": "Find by",
                "required": True,
                "options": ["text", "resource_id"],
            },
            "value": {"type": "text", "label": "Value", "required": True},
            "timeout": {"type": "number", "label": "Timeout (ms)", "required": False, "default": 5000},
        },
    },
    "adb_shell": {
        "label": "ADB Shell",
        "category": "Debug",
        "config": {
            "command": {"type": "text", "label": "Shell command", "required": True},
        },
    },
}


class AutomationMixin:
    _automations = []
    _automation_runs = []
    _active_runs = {}  # run_id -> cancel_event

    def get_step_types(self):
        return STEP_TYPES

    # ---------------------------------------------------------------
    # Automation CRUD
    # ---------------------------------------------------------------
    def create_automation(self, name, description="", steps=None, tags=None):
        automation = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "steps": steps or [],
            "tags": tags or [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._automations.append(automation)
        logger.info(f"Created automation '{name}' ({automation['id']})")
        return automation

    def get_automation(self, automation_id):
        return next((a for a in self._automations if a["id"] == automation_id), None)

    def list_automations(self):
        return list(self._automations)

    def update_automation(self, automation_id, updates):
        automation = self.get_automation(automation_id)
        if not automation:
            return None
        updates["updated_at"] = time.time()
        automation.update(updates)
        return automation

    def delete_automation(self, automation_id):
        before = len(self._automations)
        self._automations = [a for a in self._automations if a["id"] != automation_id]
        deleted = len(self._automations) < before
        if deleted:
            logger.info(f"Deleted automation {automation_id}")
        return deleted

    # ---------------------------------------------------------------
    # Execution
    # ---------------------------------------------------------------
    def execute_automation(self, automation_id, device_id):
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")

        steps = automation.get("steps", [])
        run_record = {
            "id": str(uuid.uuid4()),
            "automation_id": automation_id,
            "automation_name": automation.get("name", ""),
            "device_id": device_id,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "total_steps": len(steps),
            "completed_steps": 0,
            "current_step_index": 0,
            "step_results": [],
            "error": None,
        }
        self._automation_runs.append(run_record)

        cancel_event = threading.Event()
        self._active_runs[run_record["id"]] = cancel_event

        thread = threading.Thread(
            target=self._run_automation_thread,
            args=(run_record, steps, device_id, cancel_event),
            daemon=True,
        )
        thread.start()

        return run_record

    def _run_automation_thread(self, run_record, steps, device_id, cancel_event):
        step_results = []
        completed = 0

        for idx, step in enumerate(steps):
            if cancel_event.is_set():
                run_record.update({
                    "status": "cancelled",
                    "finished_at": time.time(),
                    "completed_steps": completed,
                    "current_step_index": idx,
                    "step_results": step_results,
                })
                self._active_runs.pop(run_record["id"], None)
                return

            run_record["current_step_index"] = idx

            start_ts = time.time()
            result = {
                "step_id": step.get("id", str(idx)),
                "step_type": step.get("type", "unknown"),
                "label": step.get("label", ""),
                "status": "running",
                "output": None,
                "error": None,
                "duration_ms": 0,
            }

            try:
                output = self._execute_step(step, device_id)
                elapsed = int((time.time() - start_ts) * 1000)
                result["status"] = "completed"
                result["output"] = str(output) if output else None
                result["duration_ms"] = elapsed
                completed += 1
            except Exception as e:
                elapsed = int((time.time() - start_ts) * 1000)
                result["status"] = "failed"
                result["error"] = str(e)
                result["duration_ms"] = elapsed
                step_results.append(result)
                # Mark remaining steps as skipped
                for remaining in steps[idx + 1:]:
                    step_results.append({
                        "step_id": remaining.get("id", ""),
                        "step_type": remaining.get("type", "unknown"),
                        "label": remaining.get("label", ""),
                        "status": "skipped",
                        "output": None,
                        "error": None,
                        "duration_ms": 0,
                    })
                run_record.update({
                    "status": "failed",
                    "finished_at": time.time(),
                    "completed_steps": completed,
                    "current_step_index": idx,
                    "step_results": step_results,
                    "error": str(e),
                })
                self._active_runs.pop(run_record["id"], None)
                return

            step_results.append(result)
            run_record["completed_steps"] = completed
            run_record["step_results"] = step_results

        run_record.update({
            "status": "completed",
            "finished_at": time.time(),
            "completed_steps": completed,
            "current_step_index": len(steps),
            "step_results": step_results,
        })
        self._active_runs.pop(run_record["id"], None)

    def _execute_step(self, step, device_id):
        step_type = step.get("type")
        config = step.get("config", {})

        if step_type == "tap":
            x = int(config["x"])
            y = int(config["y"])
            self.click(x, y, device_id)
            return f"Tapped ({x}, {y})"

        elif step_type == "tap_by_text":
            text = config["text"]
            self.click_by_text(text, device_id)
            return f"Tapped element with text '{text}'"

        elif step_type == "tap_by_resource_id":
            rid = config["resource_id"]
            self.click_by_resource_id(rid, device_id)
            return f"Tapped element '{rid}'"

        elif step_type == "swipe":
            direction = config.get("direction", "up")
            duration = int(config.get("duration", 500))
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
            d.swipe(*coords, duration=duration / 1000)
            return f"Swiped {direction}"

        elif step_type == "type_text":
            text = config["text"]
            d = self.get_device(device_id)
            d.send_keys(text)
            return f"Typed '{text}'"

        elif step_type == "press_key":
            key = config["key"]
            self.press_action(key, device_id)
            return f"Pressed '{key}'"

        elif step_type == "open_app":
            package = config["package"]
            d = self.get_device(device_id)
            d.app_start(package)
            return f"Opened {package}"

        elif step_type == "close_app":
            package = config["package"]
            self.run_adb_command(f"shell am force-stop {package}", device=device_id)
            return f"Closed {package}"

        elif step_type == "open_url":
            url = config["url"]
            self.run_adb_command([
                "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url
            ], device=device_id)
            return f"Opened URL {url}"

        elif step_type == "wait":
            delay = int(config.get("delay", 1000))
            time.sleep(delay / 1000)
            return f"Waited {delay}ms"

        elif step_type == "wait_for_element":
            by = config.get("by", "text")
            value = config["value"]
            timeout = int(config.get("timeout", 10000))
            timeout_secs = timeout / 1000
            if by == "text":
                found = self.exists_by_text(value, device_id, timeout=timeout_secs)
            else:
                found = self.exists_by_resource_id(value, device_id, timeout=timeout_secs)
            if not found:
                raise Exception(f"Element not found by {by}='{value}' within {timeout}ms")
            return f"Found element {by}='{value}'"

        elif step_type == "screenshot":
            data = self.take_screenshot(device_id)
            if data:
                return f"Screenshot captured ({len(data)} bytes)"
            raise Exception("Screenshot failed")

        elif step_type == "assert_element":
            by = config.get("by", "text")
            value = config["value"]
            timeout = int(config.get("timeout", 5000))
            timeout_secs = timeout / 1000
            if by == "text":
                found = self.exists_by_text(value, device_id, timeout=timeout_secs)
            else:
                found = self.exists_by_resource_id(value, device_id, timeout=timeout_secs)
            if not found:
                raise AssertionError(f"Assertion failed: element {by}='{value}' not found")
            return f"Assertion passed: {by}='{value}' exists"

        elif step_type == "adb_shell":
            command = config["command"]
            output = self.run_adb_command(f"shell {command}", device=device_id)
            return output or "(no output)"

        else:
            raise ValueError(f"Unknown step type: {step_type}")

    # ---------------------------------------------------------------
    # Run management
    # ---------------------------------------------------------------
    def cancel_automation_run(self, run_id):
        cancel_event = self._active_runs.get(run_id)
        if cancel_event:
            cancel_event.set()
            return True
        return False

    def get_automation_run(self, run_id):
        return next((r for r in self._automation_runs if r["id"] == run_id), None)

    def list_automation_runs(self, automation_id=None, device_id=None, limit=50):
        runs = list(self._automation_runs)
        if automation_id:
            runs = [r for r in runs if r.get("automation_id") == automation_id]
        if device_id:
            runs = [r for r in runs if r.get("device_id") == device_id]
        runs.sort(key=lambda r: r.get("started_at", 0), reverse=True)
        return runs[:limit]
