# Add a New Automation Step Type

Add a new step type to the DeviceKit automation engine. The user will provide: **$ARGUMENTS**

## Context

Read `backend/devicekit/mixins/automation.py` first. Step types are defined in the `STEP_TYPES` dict at the top of the file and executed in the `_execute_step` method.

## Steps

1. **Add the step type definition** to the `STEP_TYPES` dict in `backend/devicekit/mixins/automation.py`:

```python
"<step_key>": {
    "label": "<Human-readable label>",
    "category": "<Interaction|Apps|Timing|Debug>",  # or a new category
    "config": {
        "<param_name>": {
            "type": "<text|number|select>",
            "label": "<Human-readable label>",
            "required": True/False,
            # For select type: "options": [{"value": "x", "label": "X"}, ...]
            # For number type with default: "default": 1000
        },
    },
},
```

2. **Add execution logic** in the `_execute_step` method of `AutomationMixin`:
   - Add an `elif step_type == "<step_key>":` branch
   - Extract config values from `config = step.get('config', {})`
   - Call the appropriate mixin methods (ADB, UIAutomator2, etc.)
   - Return a descriptive output string
   - Raise exceptions on failure (the runner catches them and marks step as failed)

3. **Verify** by reading back automation.py to confirm the step type is in both `STEP_TYPES` and `_execute_step`.

## Notes

- The frontend AutomationEditor (`frontend/src/views/AutomationEditor.jsx`) dynamically renders config fields based on `STEP_TYPES`, so no frontend changes are needed -- new step types appear automatically.
- Step types are fetched via `GET /automations/step-types` which returns the `STEP_TYPES` dict directly.
- Categories are used to group steps in the step picker modal.
