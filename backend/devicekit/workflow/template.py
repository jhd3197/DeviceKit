"""``{{path.to.field}}`` interpolation — port of tramo runtime ``template.ts``.

Roots:
  - ``vars.…``    → the run's variable map
  - ``steps.…``   → completed-node outputs, keyed by node id *and* slug
  - ``trigger.…`` → the run's trigger payload (DeviceKit extension — tramo reaches the
    trigger through the root node's input; plan 22 names ``{{trigger.*}}`` explicitly,
    so both spellings work here)
  - anything else → walked against the immediate input value (context), with a legacy
    fallback to the flat ``vars`` bag so pre-plan-22 ``{{store_as_name}}`` refs keep
    resolving.

Missing paths render as an empty string (forgiving on purpose, same as tramo).
"""
import json
import re

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def parse_maybe_json(value):
    """Parse a string as JSON when possible; pass non-strings through; empty → None."""
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if trimmed == "":
        return None
    try:
        return json.loads(trimmed)
    except (ValueError, TypeError):
        return value


def _walk(cursor, path):
    for seg in path:
        if cursor is None:
            return None
        if isinstance(cursor, dict):
            cursor = cursor.get(seg)
        elif isinstance(cursor, (list, tuple)):
            try:
                cursor = cursor[int(seg)]
            except (ValueError, TypeError, IndexError):
                return None
        else:
            return None
    return cursor


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    try:
        return json.dumps(value, default=str)
    except (ValueError, TypeError):
        return str(value)


def render_template(template, context=None, variables=None, steps=None, trigger=None):
    """Render every ``{{…}}`` token in ``template``. Non-strings pass through."""
    if not isinstance(template, str) or "{{" not in template:
        return template

    def replace(match):
        segments = [s.strip() for s in str(match.group(1)).split(".")]
        if segments and segments[0] == "vars" and variables is not None:
            cursor, path = variables, segments[1:]
        elif segments and segments[0] == "steps" and steps is not None:
            cursor, path = steps, segments[1:]
        elif segments and segments[0] == "trigger":
            cursor, path = trigger, segments[1:]
        else:
            cursor, path = context, segments
            # Legacy flat-variable fallback: `{{otp}}` captured via store_as.
            if (len(path) == 1 and variables is not None
                    and not (isinstance(cursor, dict) and path[0] in cursor)
                    and path[0] in variables):
                return _stringify(variables[path[0]])
        if not path:
            return _stringify(cursor)
        return _stringify(_walk(cursor, path))

    return _TEMPLATE_RE.sub(replace, template)


def render_config(config, context=None, variables=None, steps=None, trigger=None):
    """Recursively render string values in a step/node config. Additive — configs with
    no tokens come back unchanged."""
    if isinstance(config, str):
        return render_template(config, context, variables, steps, trigger)
    if isinstance(config, dict):
        return {k: render_config(v, context, variables, steps, trigger)
                for k, v in config.items()}
    if isinstance(config, list):
        return [render_config(v, context, variables, steps, trigger) for v in config]
    return config
