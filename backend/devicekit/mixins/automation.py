import uuid
import time
import re
import logging
import threading
import base64
import copy

from devicekit.db import session_scope
from devicekit.models import Automation, AutomationRun, AutomationSchedule
from devicekit.jobs.service import JobService

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
    "file_operation": {
        "label": "File Operation",
        "category": "Debug",
        "config": {
            "operation": {"type": "select", "label": "Operation", "required": True, "options": ["push", "pull", "delete"]},
            "local_path": {"type": "text", "label": "Local path (host)", "required": False},
            "remote_path": {"type": "text", "label": "Remote path (device)", "required": True},
        },
    },
    "screenshot_assert": {
        "label": "Screenshot Assert",
        "category": "Visual",
        "config": {
            "baseline_id": {"type": "text", "label": "Baseline ID", "required": False},
            "threshold": {"type": "number", "label": "SSIM threshold (%)", "required": False, "default": 95},
            "use_ai": {"type": "select", "label": "AI diff analysis", "required": False, "options": ["off", "on"], "default": "on"},
        },
    },
    "require_capability": {
        "label": "Require Capability",
        "category": "Control",
        "config": {
            "capability": {"type": "text", "label": "Capability key (e.g. screen_record)", "required": True},
            "mode": {"type": "select", "label": "If missing", "required": False,
                     "options": ["fail", "warn"], "default": "fail"},
        },
    },
}


# ---------------------------------------------------------------------------
# Step dispatch registry
# ---------------------------------------------------------------------------
# Every step type carries an ``execute(client, config, device_id) -> output`` callable so
# core and extension steps run through one path (``_execute_step``) — no ``elif`` chain to
# edit when an extension contributes a step type. Executors are plain module functions
# attached to the metadata entries below; ``get_step_types`` strips the callable before
# serializing the metadata for the AutomationEditor.

def _exec_tap(client, config, device_id):
    x = int(config["x"])
    y = int(config["y"])
    client.click(x, y, device_id)
    return f"Tapped ({x}, {y})"


def _exec_tap_by_text(client, config, device_id):
    text = config["text"]
    client.click_by_text(text, device_id)
    return f"Tapped element with text '{text}'"


def _exec_tap_by_resource_id(client, config, device_id):
    rid = config["resource_id"]
    client.click_by_resource_id(rid, device_id)
    return f"Tapped element '{rid}'"


def _exec_swipe(client, config, device_id):
    direction = config.get("direction", "up")
    duration = int(config.get("duration", 500))
    d = client.get_device(device_id)
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


def _exec_type_text(client, config, device_id):
    text = config["text"]
    d = client.get_device(device_id)
    d.send_keys(text)
    return f"Typed '{text}'"


def _exec_press_key(client, config, device_id):
    key = config["key"]
    client.press_action(key, device_id)
    return f"Pressed '{key}'"


def _exec_open_app(client, config, device_id):
    package = config["package"]
    d = client.get_device(device_id)
    d.app_start(package)
    return f"Opened {package}"


def _exec_close_app(client, config, device_id):
    package = config["package"]
    client.run_adb_command(f"shell am force-stop {package}", device=device_id)
    return f"Closed {package}"


def _exec_open_url(client, config, device_id):
    url = config["url"]
    client.run_adb_command([
        "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url
    ], device=device_id)
    return f"Opened URL {url}"


def _exec_wait(client, config, device_id):
    delay = int(config.get("delay", 1000))
    time.sleep(delay / 1000)
    return f"Waited {delay}ms"


def _exec_wait_for_element(client, config, device_id):
    by = config.get("by", "text")
    value = config["value"]
    timeout = int(config.get("timeout", 10000))
    timeout_secs = timeout / 1000
    if by == "text":
        found = client.exists_by_text(value, device_id, timeout=timeout_secs)
    else:
        found = client.exists_by_resource_id(value, device_id, timeout=timeout_secs)
    if not found:
        raise Exception(f"Element not found by {by}='{value}' within {timeout}ms")
    return f"Found element {by}='{value}'"


def _exec_screenshot(client, config, device_id):
    data = client.take_screenshot(device_id)
    if data:
        return f"Screenshot captured ({len(data)} bytes)"
    raise Exception("Screenshot failed")


def _exec_assert_element(client, config, device_id):
    by = config.get("by", "text")
    value = config["value"]
    timeout = int(config.get("timeout", 5000))
    timeout_secs = timeout / 1000
    if by == "text":
        found = client.exists_by_text(value, device_id, timeout=timeout_secs)
    else:
        found = client.exists_by_resource_id(value, device_id, timeout=timeout_secs)
    if not found:
        raise AssertionError(f"Assertion failed: element {by}='{value}' not found")
    return f"Assertion passed: {by}='{value}' exists"


def _exec_adb_shell(client, config, device_id):
    command = config["command"]
    output = client.run_adb_command(f"shell {command}", device=device_id)
    return output or "(no output)"


def _exec_file_operation(client, config, device_id):
    operation = config.get("operation", "push")
    local_path = config.get("local_path", "")
    remote_path = config["remote_path"]
    if operation == "push":
        if not local_path:
            raise ValueError("local_path is required for push operation")
        output = client.run_adb_command(f"push {local_path} {remote_path}", device=device_id)
        return output or f"Pushed {local_path} to {remote_path}"
    elif operation == "pull":
        if not local_path:
            raise ValueError("local_path is required for pull operation")
        output = client.run_adb_command(f"pull {remote_path} {local_path}", device=device_id)
        return output or f"Pulled {remote_path} to {local_path}"
    elif operation == "delete":
        output = client.run_adb_command(f"shell rm -f {remote_path}", device=device_id)
        return output or f"Deleted {remote_path}"
    else:
        raise ValueError(f"Unknown file operation: {operation}")


def _exec_screenshot_assert(client, config, device_id):
    baseline_id = config.get("baseline_id", "")
    threshold = float(config.get("threshold", 95))
    use_ai = config.get("use_ai", "on") == "on"
    screenshot_data = client.take_screenshot(device_id)
    if not screenshot_data:
        raise Exception("Failed to capture screenshot for visual assertion")
    result = client.compare_screenshot(
        screenshot_data, baseline_id=baseline_id,
        threshold=threshold, use_ai=use_ai, device_id=device_id,
    )
    if result.get("passed"):
        return f"Visual assertion passed (SSIM={result.get('ssim', 0):.1f}%, verdict={result.get('verdict', 'pass')})"
    else:
        msg = f"Visual assertion failed (SSIM={result.get('ssim', 0):.1f}%, threshold={threshold}%"
        if result.get("ai_analysis"):
            msg += f", AI: {result['ai_analysis'][:200]}"
        msg += ")"
        raise AssertionError(msg)


def _exec_require_capability(client, config, device_id):
    """Gate a run on a device capability (plan 07). ``fail`` (default) aborts the run when
    the capability is missing; ``warn`` continues with a note. Fleet-level "skip the device"
    is achieved upstream by targeting with an FQL ``can.*`` filter."""
    cap = config["capability"]
    mode = (config.get("mode") or "fail").lower()
    caps = {}
    if hasattr(client, "get_agent_capabilities"):
        caps = client.get_agent_capabilities(device_id) or {}
    if bool(caps.get(cap)):
        return f"Capability '{cap}' present"
    msg = f"Device '{device_id}' lacks required capability '{cap}'"
    if mode == "warn":
        return f"WARN: {msg} (continuing)"
    raise ValueError(msg)


_CORE_EXECUTORS = {
    "tap": _exec_tap,
    "tap_by_text": _exec_tap_by_text,
    "tap_by_resource_id": _exec_tap_by_resource_id,
    "swipe": _exec_swipe,
    "type_text": _exec_type_text,
    "press_key": _exec_press_key,
    "open_app": _exec_open_app,
    "close_app": _exec_close_app,
    "open_url": _exec_open_url,
    "wait": _exec_wait,
    "wait_for_element": _exec_wait_for_element,
    "screenshot": _exec_screenshot,
    "assert_element": _exec_assert_element,
    "adb_shell": _exec_adb_shell,
    "file_operation": _exec_file_operation,
    "screenshot_assert": _exec_screenshot_assert,
    "require_capability": _exec_require_capability,
}

# Attach each executor to its metadata entry, making STEP_TYPES the dispatch registry.
for _type_name, _executor in _CORE_EXECUTORS.items():
    STEP_TYPES[_type_name]["execute"] = _executor


class AutomationMixin:
    _active_runs = {}  # run_id -> cancel_event (ephemeral: live cancel handles)
    _run_jobs = {}  # run_id -> job_id (ephemeral: lets cancel find a still-queued run's job)
    _recording_sessions = {}  # session_id -> {device_id, actions, started_at}
    _device_run_locks = {}  # device_id -> threading.Lock (per-device run serialization)
    _device_run_locks_guard = threading.Lock()
    _ext_step_types = {}  # type_name -> spec (contributed by extensions; overlays STEP_TYPES)

    def _device_run_lock(self, device_id):
        """A per-device lock so two automation jobs never drive the same device at once
        (fleet-wide parallelism is still allowed — different devices run concurrently)."""
        with self._device_run_locks_guard:
            lock = self._device_run_locks.get(device_id)
            if lock is None:
                lock = threading.Lock()
                self._device_run_locks[device_id] = lock
            return lock

    # ---------------------------------------------------------------
    # Step-type dispatch registry
    # ---------------------------------------------------------------
    def step_type_registry(self):
        """Merged view of core + extension step types (entries include ``execute``)."""
        if self._ext_step_types:
            return {**STEP_TYPES, **self._ext_step_types}
        return STEP_TYPES

    def get_step_types(self):
        """Metadata for the AutomationEditor — the ``execute`` callable is stripped so the
        registry serializes cleanly to JSON."""
        out = {}
        for name, spec in self.step_type_registry().items():
            out[name] = {k: v for k, v in spec.items() if k != "execute"}
        return out

    def register_step_type(self, type_name, spec):
        """Register (or replace) an extension-contributed step type. ``spec`` is the same
        metadata shape as ``STEP_TYPES`` entries plus a required ``execute`` callable
        ``execute(client, config, device_id) -> output``."""
        if "execute" not in spec or not callable(spec["execute"]):
            raise ValueError(f"Step type '{type_name}' must provide an 'execute' callable")
        self._ext_step_types[type_name] = spec
        logger.info(f"Registered extension step type '{type_name}'")

    def unregister_step_type(self, type_name):
        """Remove an extension-contributed step type (used on disable/uninstall)."""
        self._ext_step_types.pop(type_name, None)

    # ---------------------------------------------------------------
    # Automation CRUD
    # ---------------------------------------------------------------
    def create_automation(self, name, description="", steps=None, tags=None,
                          workspace_id=None, graph=None):
        now = time.time()
        with session_scope() as s:
            automation = Automation(
                id=str(uuid.uuid4()),
                name=name,
                description=description,
                steps=steps or [],
                tags=tags or [],
                created_at=now,
                updated_at=now,
                workspace_id=workspace_id,   # born-in-workspace (plan 20 part 4); None = global
                graph=graph,                 # plan 22: a tramo WorkflowDoc, or None (linear)
            )
            s.add(automation)
            s.flush()
            result = automation.to_dict()
        logger.info(f"Created automation '{name}' ({result['id']})")
        return result

    def get_automation(self, automation_id):
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            return automation.to_dict() if automation else None

    def list_automations(self, workspace_id=None):
        """List automations, narrowed to a workspace when one is active. With no workspace
        context (``workspace_id=None``) the query is unchanged (plan 20 part 4, narrow-only)."""
        from devicekit.services.workspace import scope_query
        with session_scope() as s:
            q = scope_query(s.query(Automation), Automation, workspace_id)
            return [a.to_dict() for a in q.all()]

    def update_automation(self, automation_id, updates):
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            if not automation:
                return None
            for key in ("name", "description", "steps", "tags"):
                if key in updates:
                    setattr(automation, key, updates[key])
            automation.updated_at = time.time()
            s.flush()
            return automation.to_dict()

    def delete_automation(self, automation_id):
        with session_scope() as s:
            automation = s.get(Automation, automation_id)
            if not automation:
                return False
            s.delete(automation)
        logger.info(f"Deleted automation {automation_id}")
        return True

    # ---------------------------------------------------------------
    # Execution
    # ---------------------------------------------------------------
    def execute_automation(self, automation_id, device_id, self_heal=False):
        """Create a run record and enqueue an ``automation.run`` job that executes it.

        Formerly this spawned a raw daemon thread; now the run is durable work on the job
        system — it survives a restart with a coherent status, can be retried, and appears in
        the jobs list. The step loop itself is unchanged; it just runs inside the job handler
        (``_job_run_automation``) on a bounded worker pool. Returns the queued run record
        immediately so the API still responds 201 without blocking."""
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")

        # Graph automations (plan 22) run on the workflow engine; every caller of this
        # method (routes, MCP actions, schedules) funnels through without changes.
        if automation.get("graph") and hasattr(self, "_enqueue_graph_run"):
            return self._enqueue_graph_run(automation, device_id, "manual", None,
                                           self_heal=self_heal)

        steps = automation.get("steps", [])
        run_record = {
            "id": str(uuid.uuid4()),
            "automation_id": automation_id,
            "automation_name": automation.get("name", ""),
            "device_id": device_id,
            "status": "queued",
            "started_at": time.time(),
            "finished_at": None,
            "total_steps": len(steps),
            "completed_steps": 0,
            "current_step_index": 0,
            "step_results": [],
            "error": None,
            "self_heal": self_heal,
        }
        self._save_run(run_record)

        # A thin pointer rides the queue; the steps snapshot travels in the payload so an edit
        # to the automation between enqueue and execution doesn't change what this run does.
        job = JobService.enqueue(
            "automation.run",
            payload={
                "run_id": run_record["id"],
                "automation_id": automation_id,
                "device_id": device_id,
                "self_heal": self_heal,
                "steps": steps,
            },
            max_attempts=1,  # a failed automation is a terminal outcome, not a job to retry
            owner_type="automation_run",
            owner_id=run_record["id"],
        )
        self._run_jobs[run_record["id"]] = job["id"]
        return run_record

    def _job_run_automation(self, job):
        """Job handler for ``automation.run`` — drives one run's step loop to completion.

        Registered by JobsMixin. Honors a cancel requested before pickup, serializes per
        device, and never raises for a normal step failure (that's a ``failed`` run, a
        succeeded job). Returns a compact summary as the job result."""
        payload = job.get("payload", {})
        run_id = payload.get("run_id")
        device_id = payload.get("device_id")
        steps = payload.get("steps") or []
        self_heal = payload.get("self_heal", False)
        if not run_id:
            return {"error": "missing run_id"}

        run_record = self.get_automation_run(run_id)
        if not run_record:
            return {"skipped": "run record missing"}
        if run_record.get("status") in ("cancelled", "failed", "completed"):
            # Cancelled, or reconciled-as-failed on a prior restart — do not re-run.
            return {"skipped": run_record.get("status")}

        run_record["self_heal"] = self_heal
        cancel_event = threading.Event()
        self._active_runs[run_id] = cancel_event

        try:
            lock = self._device_run_lock(device_id)
            with lock:
                if cancel_event.is_set():
                    run_record.update({"status": "cancelled", "finished_at": time.time()})
                    self._save_run(run_record)
                    return {"run_id": run_id, "status": "cancelled"}
                self._run_automation_steps(run_record, steps, device_id, cancel_event)
        except Exception as e:
            logger.error(f"Automation run {run_id} crashed: {e}")
            run_record.update({"status": "failed", "finished_at": time.time(), "error": str(e)})
            self._save_run(run_record)
            self._notify_run_failed(run_record, run_record.get("current_step_index", 0),
                                    None, str(e))
            self._active_runs.pop(run_id, None)
        finally:
            self._run_jobs.pop(run_id, None)

        final = self.get_automation_run(run_id)
        return {
            "run_id": run_id,
            "status": final.get("status") if final else None,
            "completed_steps": final.get("completed_steps") if final else None,
        }

    def _run_automation_steps(self, run_record, steps, device_id, cancel_event):
        from devicekit.mixins.nl_automation import UI_TARGETING_STEP_TYPES

        # Flip queued -> running now that a worker owns this run.
        run_record["status"] = "running"
        self._save_run(run_record)

        step_results = []
        completed = 0
        variables = {}  # run-scoped variables captured via step config `store_as`
        self_heal_enabled = run_record.get("self_heal", False)

        for idx, step in enumerate(steps):
            if cancel_event.is_set():
                run_record.update({
                    "status": "cancelled",
                    "finished_at": time.time(),
                    "completed_steps": completed,
                    "current_step_index": idx,
                    "step_results": step_results,
                })
                self._save_run(run_record)
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
                output = self._execute_step(step, device_id, variables=variables)
                elapsed = int((time.time() - start_ts) * 1000)
                result["status"] = "completed"
                result["output"] = str(output) if output else None
                result["duration_ms"] = elapsed
                self._store_step_var(variables, step, output)
                completed += 1
            except Exception as e:
                error_str = str(e)
                step_type = step.get("type", "")

                # Attempt self-healing for UI-targeting steps
                healed = False
                if self_heal_enabled and step_type in UI_TARGETING_STEP_TYPES:
                    try:
                        heal_result = self.self_heal_step(device_id, step, error_str)
                        if heal_result.get("healed"):
                            # A heal is a write-ish decision: apply it through the same
                            # confirmation gate as agent tools (plan 13). Supervised runs
                            # pause for approval; autonomous auto-applies + audits; observe
                            # refuses. Falls back to direct execution if no gate is composed.
                            healed_step = heal_result["new_step"]
                            reasoning = heal_result.get("reasoning", "")
                            exec_box = {}

                            def _apply_heal():
                                exec_box["output"] = self._execute_step(healed_step, device_id, variables=variables)
                                exec_box["ran"] = True
                                return str(exec_box["output"]) if exec_box["output"] else ""

                            if hasattr(self, "gate_tool_call"):
                                gate_msg = self.gate_tool_call(
                                    device_id, "self_heal",
                                    {"proposed_step": healed_step, "reason": reasoning},
                                    {"is_write": True, "category": "self_heal",
                                     "label": "Apply self-heal"},
                                    source="self_heal", real_fn=_apply_heal)
                            else:
                                _apply_heal()
                                gate_msg = ""

                            if exec_box.get("ran"):
                                output = exec_box["output"]
                                elapsed = int((time.time() - start_ts) * 1000)
                                result["status"] = "completed"
                                result["output"] = str(output) if output else None
                                result["duration_ms"] = elapsed
                                result["healed"] = True
                                result["original_step"] = copy.deepcopy(step)
                                result["healed_step"] = healed_step
                                result["heal_reasoning"] = reasoning
                                self._store_step_var(variables, step, output)
                                completed += 1
                                healed = True
                                self._notify_run_healed(run_record, idx, result.get("heal_reasoning", ""))
                            else:
                                # Gate denied/timed out — the heal was not applied.
                                result["healed"] = False
                                result["heal_reasoning"] = gate_msg or "Heal not approved"
                        else:
                            # Heal attempted but failed
                            result["healed"] = False
                            result["heal_reasoning"] = heal_result.get("reasoning", "Could not find element")
                    except Exception as heal_err:
                        logger.warning(f"Self-heal error for step {idx}: {heal_err}")
                        result["healed"] = False
                        result["heal_reasoning"] = f"Heal error: {heal_err}"

                if not healed:
                    elapsed = int((time.time() - start_ts) * 1000)
                    result["status"] = "failed"
                    result["error"] = error_str
                    result["duration_ms"] = elapsed
                    # Best-effort screenshot capture on failure
                    try:
                        screenshot_data = self.take_screenshot(device_id)
                        if screenshot_data:
                            result["failure_screenshot"] = base64.b64encode(screenshot_data).decode('ascii')
                    except Exception:
                        pass
                    # Auto-generate debug bundle on failure
                    try:
                        bundle = self.generate_debug_bundle(
                            device_id,
                            trigger='automation_failure',
                            context={
                                'automation_id': run_record.get('automation_id'),
                                'automation_name': run_record.get('automation_name'),
                                'run_id': run_record.get('id'),
                                'step_index': idx,
                                'step_type': step.get('type', ''),
                                'step_label': step.get('label', ''),
                                'error': error_str,
                            },
                        )
                        result["debug_bundle_id"] = bundle.get('id')
                        logger.info(f"Auto-generated debug bundle {bundle.get('id')} for failed step {idx}")
                    except Exception as bundle_err:
                        logger.warning(f"Failed to generate debug bundle: {bundle_err}")
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
                        "error": error_str,
                    })
                    self._save_run(run_record)
                    self._notify_run_failed(run_record, idx, step, error_str)
                    self._active_runs.pop(run_record["id"], None)
                    return

            step_results.append(result)
            run_record["completed_steps"] = completed
            run_record["step_results"] = step_results
            self._save_run(run_record)

        run_record.update({
            "status": "completed",
            "finished_at": time.time(),
            "completed_steps": completed,
            "current_step_index": len(steps),
            "step_results": step_results,
        })
        self._save_run(run_record)
        self._active_runs.pop(run_record["id"], None)

    def _execute_step(self, step, device_id, variables=None):
        step_type = step.get("type")
        config = step.get("config", {})
        # Run-scoped variables: interpolate {{name}} placeholders in the step config against
        # values captured by earlier steps (via their config's ``store_as``). Additive — a
        # config with no placeholders is returned unchanged.
        if variables:
            config = self._interpolate_vars(config, variables)

        spec = self.step_type_registry().get(step_type)
        if spec is None:
            raise ValueError(f"Unknown step type: {step_type}")
        executor = spec.get("execute")
        if executor is None or not callable(executor):
            raise ValueError(f"Step type '{step_type}' has no executor")
        return executor(self, config, device_id)

    # Placeholder like {{otp}} — a simple, safe run-scoped variable reference. A missing
    # variable is left literal rather than raising, so a typo can't crash a run.
    _VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}")

    def _interpolate_vars(self, value, variables):
        if isinstance(value, str):
            return self._VAR_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), value)
        if isinstance(value, dict):
            return {k: self._interpolate_vars(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._interpolate_vars(v, variables) for v in value]
        return value

    @staticmethod
    def _store_step_var(variables, step, output):
        """If a step's config declares ``store_as``, capture its output into the run's
        variable bag so later steps can reference it as ``{{name}}``.

        Scalars store verbatim as ``str(output)`` (unchanged). A **structured** output (dict or
        list — e.g. ``serp_search``'s ``{results: [...]}``) is stored as JSON under ``{name}``,
        and, for a dict, each scalar top-level value is also exposed as ``{name}_{key}`` so an
        automation can chain on it (``{{serp_device_id}}``); a ``{results:[{url:...}]}`` shape
        additionally yields ``{name}_top_url`` — the "open first result" primitive. The run's
        ``{{name}}`` interpolation is flat-string only, so these derived keys are how structured
        data becomes referenceable without a nested-path variable system."""
        import json as _json

        name = (step.get("config") or {}).get("store_as")
        if not name:
            return
        name = str(name)
        if isinstance(output, dict):
            try:
                variables[name] = _json.dumps(output, default=str)
            except Exception:
                variables[name] = str(output)
            for key, val in output.items():
                if isinstance(val, (str, int, float, bool)):
                    variables[f"{name}_{key}"] = str(val)
            results = output.get("results")
            if (isinstance(results, list) and results
                    and isinstance(results[0], dict) and results[0].get("url")):
                variables[f"{name}_top_url"] = str(results[0]["url"])
        elif isinstance(output, list):
            try:
                variables[name] = _json.dumps(output, default=str)
            except Exception:
                variables[name] = str(output)
        else:
            variables[name] = "" if output is None else str(output)

    # ---------------------------------------------------------------
    # Run management
    # ---------------------------------------------------------------
    def cancel_automation_run(self, run_id):
        # Actively running on a worker: signal the cooperative cancel event; the step loop
        # marks the run cancelled at the next step boundary.
        cancel_event = self._active_runs.get(run_id)
        if cancel_event:
            cancel_event.set()
            return True
        # Still queued (no worker yet): mark it cancelled and cancel the underlying job so the
        # consumer skips the message when it arrives.
        run = self.get_automation_run(run_id)
        if not run or run.get("status") not in ("queued", "running"):
            return False
        run["status"] = "cancelled"
        run["finished_at"] = time.time()
        self._save_run(run)
        job_id = self._run_jobs.get(run_id) or self._find_run_job(run_id)
        if job_id:
            try:
                JobService.cancel(job_id)
            except Exception:
                pass
        return True

    # ---------------------------------------------------------------
    # Notification producer hooks (plan 06). Best-effort — a notification problem must
    # never affect a run. ``notify_event`` is provided by NotificationsMixin on the
    # composite and is itself exception-safe; the hasattr guard keeps AutomationMixin
    # usable in isolation (tests compose a bare subset).
    # ---------------------------------------------------------------
    def _notify_run_failed(self, run_record, step_index, step, error):
        if not hasattr(self, "notify_event"):
            return
        self.notify_event(
            "automation.run.failed",
            data={
                "automation_name": run_record.get("automation_name") or "automation",
                "automation_id": run_record.get("automation_id"),
                "run_id": run_record.get("id"),
                "device_id": run_record.get("device_id"),
                "step_index": step_index,
                "step_type": (step or {}).get("type", "") if step else "",
                "error": (error or "")[:300],
            },
            subject_type="automation_run", subject_id=run_record.get("id"))

    def _notify_run_healed(self, run_record, step_index, reasoning):
        if not hasattr(self, "notify_event"):
            return
        self.notify_event(
            "automation.run.healed",
            data={
                "automation_name": run_record.get("automation_name") or "automation",
                "automation_id": run_record.get("automation_id"),
                "run_id": run_record.get("id"),
                "device_id": run_record.get("device_id"),
                "step_index": step_index,
                "heal_reasoning": (reasoning or "")[:300],
            },
            subject_type="automation_run", subject_id=run_record.get("id"))

    def _find_run_job(self, run_id):
        """Locate the ``automation.run`` job for a run (in-memory map lost after a restart)."""
        jobs = JobService.list(owner_type="automation_run", owner_id=run_id, limit=1)
        return jobs[0]["id"] if jobs else None

    def _save_run(self, run_record):
        """Upsert an automation-run row from the live in-memory record. Called at
        creation and after every step/terminal transition so polling and restart both
        see current progress."""
        with session_scope() as s:
            row = s.get(AutomationRun, run_record["id"])
            if not row:
                row = AutomationRun(id=run_record["id"])
                s.add(row)
            row.automation_id = run_record.get("automation_id")
            row.automation_name = run_record.get("automation_name", "")
            row.device_id = run_record.get("device_id")
            row.status = run_record.get("status")
            row.started_at = run_record.get("started_at")
            row.finished_at = run_record.get("finished_at")
            row.total_steps = run_record.get("total_steps", 0)
            row.completed_steps = run_record.get("completed_steps", 0)
            row.current_step_index = run_record.get("current_step_index", 0)
            row.step_results = run_record.get("step_results", [])
            row.error = run_record.get("error")
            row.self_heal = run_record.get("self_heal", False)
            row.kind = run_record.get("kind", "linear")
            row.trigger = run_record.get("trigger")

    def get_automation_run(self, run_id):
        with session_scope() as s:
            run = s.get(AutomationRun, run_id)
            return run.to_dict() if run else None

    def list_automation_runs(self, automation_id=None, device_id=None, limit=50):
        with session_scope() as s:
            q = s.query(AutomationRun)
            if automation_id:
                q = q.filter(AutomationRun.automation_id == automation_id)
            if device_id:
                q = q.filter(AutomationRun.device_id == device_id)
            q = q.order_by(AutomationRun.started_at.desc()).limit(limit)
            return [r.to_dict() for r in q.all()]

    # ---------------------------------------------------------------
    # Recording
    # ---------------------------------------------------------------
    def start_recording(self, device_id):
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "device_id": device_id,
            "actions": [],
            "started_at": time.time(),
        }
        self._recording_sessions[session_id] = session
        logger.info(f"Started recording session {session_id} for device {device_id}")
        return session

    def stop_recording(self, session_id):
        session = self._recording_sessions.pop(session_id, None)
        if not session:
            raise ValueError(f"Recording session {session_id} not found")
        steps = []
        for idx, action in enumerate(session["actions"]):
            step = self._action_to_step(action, idx)
            if step:
                steps.append(step)
        logger.info(f"Stopped recording session {session_id}: {len(steps)} steps")
        return steps

    def record_action(self, session_id, action):
        session = self._recording_sessions.get(session_id)
        if not session:
            raise ValueError(f"Recording session {session_id} not found")
        action["recorded_at"] = time.time()
        session["actions"].append(action)
        return len(session["actions"])

    def _action_to_step(self, action, index):
        action_type = action.get("type")
        step = {
            "id": str(uuid.uuid4()),
            "order": index,
        }
        if action_type == "tap":
            step["type"] = "tap"
            step["label"] = f"Tap ({action.get('x')}, {action.get('y')})"
            step["config"] = {"x": action.get("x", 0), "y": action.get("y", 0)}
        elif action_type == "swipe":
            step["type"] = "swipe"
            direction = action.get("direction", "up")
            step["label"] = f"Swipe {direction}"
            step["config"] = {
                "direction": direction,
                "duration": action.get("duration", 500),
            }
        elif action_type == "press":
            step["type"] = "press_key"
            key = action.get("key", "home")
            step["label"] = f"Press {key}"
            step["config"] = {"key": key}
        elif action_type == "type_text":
            step["type"] = "type_text"
            step["label"] = f"Type '{action.get('text', '')}'"
            step["config"] = {"text": action.get("text", "")}
        else:
            return None
        return step

    # ---------------------------------------------------------------
    # Scheduling
    # ---------------------------------------------------------------
    def create_schedule(self, automation_id, device_id, interval_minutes, enabled=True):
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")
        now = time.time()
        with session_scope() as s:
            schedule = AutomationSchedule(
                id=str(uuid.uuid4()),
                automation_id=automation_id,
                automation_name=automation.get("name", ""),
                device_id=device_id,
                interval_minutes=interval_minutes,
                enabled=enabled,
                last_run_at=None,
                next_run_at=now + interval_minutes * 60,
                created_at=now,
            )
            s.add(schedule)
            s.flush()
            result = schedule.to_dict()
        logger.info(f"Created schedule {result['id']} for automation '{automation.get('name')}'")
        return result

    def get_schedule(self, schedule_id):
        with session_scope() as s:
            schedule = s.get(AutomationSchedule, schedule_id)
            return schedule.to_dict() if schedule else None

    def list_schedules(self, automation_id=None):
        with session_scope() as s:
            q = s.query(AutomationSchedule)
            if automation_id:
                q = q.filter(AutomationSchedule.automation_id == automation_id)
            return [sch.to_dict() for sch in q.all()]

    def update_schedule(self, schedule_id, updates):
        with session_scope() as s:
            schedule = s.get(AutomationSchedule, schedule_id)
            if not schedule:
                return None
            for key in ("interval_minutes", "enabled", "device_id"):
                if key in updates:
                    setattr(schedule, key, updates[key])
            if "interval_minutes" in updates:
                schedule.next_run_at = time.time() + updates["interval_minutes"] * 60
            s.flush()
            result = schedule.to_dict()
        return result

    def delete_schedule(self, schedule_id):
        with session_scope() as s:
            schedule = s.get(AutomationSchedule, schedule_id)
            if not schedule:
                return False
            s.delete(schedule)
        logger.info(f"Deleted schedule {schedule_id}")
        return True

    def _job_schedule_tick(self, job):
        """Job handler for ``automation.schedule.tick`` — the unified replacement for the old
        per-mixin scheduler daemon. The always-on JobScheduler fires this every 30s; it
        enqueues an ``automation.run`` job for every due schedule and advances its clock."""
        return {"fired": self.run_due_automation_schedules()}

    def run_due_automation_schedules(self):
        """Enqueue a run for every enabled schedule whose ``next_run_at`` has passed, then
        advance its ``next_run_at``. Reads the DB each tick (short-lived session) so restarts
        and external edits are always reflected. Returns the number fired."""
        now = time.time()
        with session_scope() as s:
            due = (
                s.query(AutomationSchedule)
                .filter(AutomationSchedule.enabled == True)  # noqa: E712
                .filter(AutomationSchedule.next_run_at <= now)
                .all()
            )
            due_specs = [
                (sch.id, sch.automation_id, sch.device_id, sch.interval_minutes)
                for sch in due
            ]
        fired = 0
        for sched_id, automation_id, device_id, interval_minutes in due_specs:
            try:
                self.execute_automation(automation_id, device_id)
                with session_scope() as s:
                    sch = s.get(AutomationSchedule, sched_id)
                    if sch:
                        sch.last_run_at = now
                        sch.next_run_at = now + (sch.interval_minutes or interval_minutes) * 60
                fired += 1
                logger.info(f"Scheduler enqueued automation {automation_id}")
            except Exception as e:
                logger.error(f"Scheduler error for {sched_id}: {e}")
        return fired

    def reconcile_interrupted_runs(self, reason="Backend restarted during run"):
        """At boot, fail any run left ``queued``/``running`` by a previous process — its
        in-memory execution is gone. Called by JobsMixin.start_job_workers so a mid-run
        restart yields a coherent 'failed' status instead of a run stuck 'running' forever.
        Returns the number reconciled."""
        now = time.time()
        with session_scope() as s:
            rows = (
                s.query(AutomationRun)
                .filter(AutomationRun.status.in_(("queued", "running")))
                .all()
            )
            n = 0
            for r in rows:
                r.status = "failed"
                r.error = reason
                r.finished_at = now
                n += 1
            return n

    # ---------------------------------------------------------------
    # Clone / Export / Import
    # ---------------------------------------------------------------
    def clone_automation(self, automation_id, new_name=None):
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")
        steps = copy.deepcopy(automation.get("steps", []))
        for step in steps:
            step["id"] = str(uuid.uuid4())
        cloned = self.create_automation(
            name=new_name or f"{automation['name']} (Copy)",
            description=automation.get("description", ""),
            steps=steps,
            tags=list(automation.get("tags", [])),
            graph=copy.deepcopy(automation.get("graph")),
        )
        logger.info(f"Cloned automation '{automation['name']}' -> '{cloned['name']}'")
        return cloned

    def export_automation(self, automation_id):
        automation = self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")
        exported = copy.deepcopy(automation)
        # webhook_token is credential-like (the token *is* the auth) — never export it.
        for key in ("id", "created_at", "updated_at", "webhook_token"):
            exported.pop(key, None)
        if exported.get("graph") is None:
            exported.pop("graph", None)
        for step in exported.get("steps", []):
            step.pop("id", None)
        return exported

    def import_automation(self, data):
        name = data.get("name", "Imported Automation")
        return self.create_automation(
            name=name,
            description=data.get("description", ""),
            steps=data.get("steps", []),
            tags=data.get("tags", []),
            graph=data.get("graph"),
        )
