import json
import logging
import base64

logger = logging.getLogger(__name__)

# Step types that target UI elements and are eligible for self-healing
UI_TARGETING_STEP_TYPES = {"tap_by_text", "tap_by_resource_id", "wait_for_element", "assert_element"}


def _build_step_schema_description():
    """Build a text description of all step types and their configs for the LLM system prompt."""
    from devicekit.mixins.automation import STEP_TYPES

    lines = ["Available automation step types:\n"]
    for step_type, definition in STEP_TYPES.items():
        config_parts = []
        for key, schema in definition.get("config", {}).items():
            req = " (required)" if schema.get("required") else ""
            type_info = schema.get("type", "text")
            if schema.get("options"):
                type_info = f"select: {schema['options']}"
            if schema.get("default") is not None:
                type_info += f", default={schema['default']}"
            config_parts.append(f"    - {key}: {type_info}{req}")
        config_block = "\n".join(config_parts) if config_parts else "    (no config)"
        lines.append(f'  "{step_type}" ({definition.get("label", step_type)}, category: {definition.get("category", "Other")}):')
        lines.append(config_block)
    return "\n".join(lines)


GENERATION_SYSTEM_PROMPT = """You are an automation step generator for Android device testing.

{step_schema}

Your job is to convert natural language descriptions into a JSON array of automation steps.

Each step must have:
- "type": one of the step type keys above
- "config": object with the required config fields for that type
- "label": a short human-readable label for the step

Respond ONLY with valid JSON in this format:
{{
  "steps": [ {{ "type": "...", "config": {{ ... }}, "label": "..." }} ],
  "explanation": "Brief explanation of what the automation does"
}}

If UI hierarchy context is provided, use actual element text/resource IDs from the hierarchy.
Do not include any markdown formatting or code fences in your response."""

REFINE_SYSTEM_PROMPT = """You are an automation step editor for Android device testing.

{step_schema}

You will receive an existing step and an instruction to modify it.
Return ONLY valid JSON with the refined step:
{{ "type": "...", "config": {{ ... }}, "label": "..." }}

Do not include any markdown formatting or code fences in your response."""

EXPLAIN_SYSTEM_PROMPT = """You are an automation documentation assistant. You will receive a list of automation steps.
Explain what the automation does in plain English, step by step. Be concise but clear.
Format as a short paragraph followed by a numbered list of what each step does."""

SELF_HEAL_SYSTEM_PROMPT = """You are an automation self-healing assistant for Android devices.

{step_schema}

A UI-targeting step has failed during automation execution. You are given:
- The failed step config
- The error message
- The current UI hierarchy (accessibility tree)

Your job is to find the correct element on the current screen and provide updated step config.

Respond ONLY with valid JSON:
{{
  "healed": true/false,
  "new_step": {{ "type": "...", "config": {{ ... }}, "label": "..." }},
  "reasoning": "Why this fix should work"
}}

If you cannot find a suitable element, set "healed" to false and explain why in "reasoning".
Do not include any markdown formatting or code fences in your response."""


class NLAutomationMixin:
    """AI-powered natural language automation generation, refinement, explanation, and self-healing."""

    def generate_automation_steps(self, description, device_id=None):
        """Generate automation steps from a natural language description."""
        from prompture import Conversation, UsageSession

        session = UsageSession()
        step_schema = _build_step_schema_description()
        system_prompt = GENERATION_SYSTEM_PROMPT.format(step_schema=step_schema)

        conv = Conversation(
            model_name=self._get_nl_model(),
            system_prompt=system_prompt,
            callbacks=self._nl_usage_callbacks(session),
        )

        user_message = f"Generate automation steps for: {description}"

        if device_id:
            try:
                hierarchy = self.fetch_ui_hierarchy(device_id)
                if hierarchy:
                    user_message += f"\n\nCurrent UI hierarchy:\n{json.dumps(hierarchy, indent=2)[:4000]}"
            except Exception as e:
                logger.warning(f"Could not fetch UI hierarchy for context: {e}")

        try:
            response = conv.ask(user_message)
            result = json.loads(response)
            return result
        except json.JSONDecodeError:
            logger.error(f"LLM returned invalid JSON for generation: {response[:200] if response else 'empty'}")
            return {"steps": [], "explanation": "Failed to parse AI response", "error": "Invalid JSON from AI"}
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"steps": [], "explanation": "", "error": str(e)}

    def refine_step(self, step, instruction, device_id=None):
        """Refine a single automation step using natural language instruction."""
        from prompture import Conversation, UsageSession

        session = UsageSession()
        step_schema = _build_step_schema_description()
        system_prompt = REFINE_SYSTEM_PROMPT.format(step_schema=step_schema)

        conv = Conversation(
            model_name=self._get_nl_model(),
            system_prompt=system_prompt,
            callbacks=self._nl_usage_callbacks(session),
        )

        user_message = f"Current step:\n{json.dumps(step, indent=2)}\n\nInstruction: {instruction}"

        if device_id:
            try:
                hierarchy = self.fetch_ui_hierarchy(device_id)
                if hierarchy:
                    user_message += f"\n\nCurrent UI hierarchy:\n{json.dumps(hierarchy, indent=2)[:4000]}"
            except Exception as e:
                logger.warning(f"Could not fetch UI hierarchy for refinement: {e}")

        try:
            response = conv.ask(user_message)
            refined = json.loads(response)
            # Preserve original step ID if present
            if "id" in step:
                refined["id"] = step["id"]
            if "order" in step:
                refined["order"] = step["order"]
            return refined
        except json.JSONDecodeError:
            logger.error(f"LLM returned invalid JSON for refinement: {response[:200] if response else 'empty'}")
            return step  # Return original on failure
        except Exception as e:
            logger.error(f"Refinement failed: {e}")
            return step

    def explain_automation(self, automation_id):
        """Generate a human-readable explanation of an automation."""
        from prompture import Conversation, UsageSession

        automation = self.get_automation(automation_id)
        if not automation:
            return {"error": "Automation not found"}

        session = UsageSession()
        conv = Conversation(
            model_name=self._get_nl_model(),
            system_prompt=EXPLAIN_SYSTEM_PROMPT,
            callbacks=self._nl_usage_callbacks(session),
        )

        steps = automation.get("steps", [])
        user_message = (
            f"Automation: {automation.get('name', 'Untitled')}\n"
            f"Description: {automation.get('description', '')}\n\n"
            f"Steps:\n{json.dumps(steps, indent=2)}"
        )

        try:
            response = conv.ask(user_message)
            return {"explanation": response, "automation_id": automation_id}
        except Exception as e:
            logger.error(f"Explain failed: {e}")
            return {"explanation": "", "error": str(e), "automation_id": automation_id}

    def fetch_ui_hierarchy(self, device_id):
        """Fetch the accessibility tree from the device via the agent app's /ui/dump endpoint."""
        import requests

        # Try agent HTTP endpoint first
        try:
            # Check for agent device data with IP info
            # Use adb forward to access the agent's UI dump endpoint
            port = self._forward_agent_port(device_id)
            resp = requests.get(f"http://127.0.0.1:{port}/ui/dump", timeout=10)
            if resp.ok:
                return resp.json()
        except Exception as e:
            logger.debug(f"Agent UI dump failed for {device_id}: {e}")

        # Fallback: use uiautomator2 dump
        try:
            d = self.get_device(device_id)
            xml = d.dump_hierarchy()
            return {"source": "uiautomator2", "xml": xml[:8000] if xml else ""}
        except Exception as e:
            logger.warning(f"UI hierarchy fallback failed for {device_id}: {e}")
            return None

    def self_heal_step(self, device_id, step, error_message):
        """Attempt to heal a failed UI-targeting step using AI."""
        from prompture import Conversation, UsageSession

        session = UsageSession()
        step_schema = _build_step_schema_description()
        system_prompt = SELF_HEAL_SYSTEM_PROMPT.format(step_schema=step_schema)

        conv = Conversation(
            model_name=self._get_nl_model(),
            system_prompt=system_prompt,
            callbacks=self._nl_usage_callbacks(session),
        )

        # Gather context
        hierarchy = None
        screenshot_b64 = None
        try:
            hierarchy = self.fetch_ui_hierarchy(device_id)
        except Exception as e:
            logger.warning(f"Could not fetch hierarchy for self-heal: {e}")

        try:
            data = self.take_screenshot(device_id)
            if data:
                screenshot_b64 = base64.b64encode(data).decode("ascii")
        except Exception:
            pass

        user_message = (
            f"Failed step:\n{json.dumps(step, indent=2)}\n\n"
            f"Error: {error_message}\n\n"
        )
        if hierarchy:
            user_message += f"Current UI hierarchy:\n{json.dumps(hierarchy, indent=2)[:6000]}\n\n"
        if screenshot_b64:
            user_message += "(Screenshot available but omitted for brevity)\n"

        try:
            response = conv.ask(user_message)
            result = json.loads(response)
            # Preserve original step metadata
            if result.get("healed") and result.get("new_step"):
                if "id" in step:
                    result["new_step"]["id"] = step["id"]
                if "order" in step:
                    result["new_step"]["order"] = step["order"]
            return result
        except json.JSONDecodeError:
            logger.error(f"Self-heal returned invalid JSON: {response[:200] if response else 'empty'}")
            return {"healed": False, "new_step": step, "reasoning": "Failed to parse AI response"}
        except Exception as e:
            logger.error(f"Self-heal failed: {e}")
            return {"healed": False, "new_step": step, "reasoning": str(e)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_nl_model(self):
        """Get the model name for NL automation features."""
        try:
            from config import PROMPTURE_DEFAULT_MODEL
            return PROMPTURE_DEFAULT_MODEL
        except ImportError:
            return "gpt-4o-mini"

    def _nl_usage_callbacks(self, session):
        """Create Prompture callbacks for usage tracking."""
        from prompture import DriverCallbacks
        return DriverCallbacks(
            on_response=session.record,
            on_error=session.record_error,
        )

    def _forward_agent_port(self, device_id):
        """Forward the agent app's HTTP port and return the local port."""
        import random
        local_port = random.randint(19000, 19999)
        try:
            self.run_adb_command(
                f"forward tcp:{local_port} tcp:9800",
                device=device_id,
            )
        except Exception:
            pass
        return local_port
