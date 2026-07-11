"""Automation step type for devicekit-serp: ``serp_search``.

Query in, a results array out — captured into a run variable via ``store_as`` so an automation
can chain "search → open first result → screenshot". Because the run's ``{{name}}`` interpolation
is flat-string only, the structured output is stored as JSON under ``{{name}}`` **and** flattened
into ``{{name}}_device_id``, ``{{name}}_engine``, ``{{name}}_count``, and — the useful one —
``{{name}}_top_url`` (the first result's URL). So a ``browser_goto`` with ``{{name}}_top_url`` opens
the first hit. (See ``AutomationMixin._store_step_var``.)

The step ignores ``device_id`` — the browser pool picks the serving device — so it runs the same
whichever device the automation targets.
"""
from .search import search as run_search

SLUG = "devicekit-serp"


def _serp_search(client, config, device_id):
    query = config.get("query")
    if not query:
        raise ValueError("query is required")
    try:
        count = int(config.get("count", 10) or 10)
    except (TypeError, ValueError):
        count = 10
    res = run_search(
        query,
        engine=config.get("engine", "google"),
        count=count,
        pool=config.get("pool", "default"),
    )
    if res.get("error"):
        # Surface parse failure as a step failure (with the debugging context) rather than a
        # silently-empty success.
        raise Exception(res["error"])
    return res


def register():
    return {
        "serp_search": {
            "label": "SERP: Search",
            "category": "Search",
            "config": {
                "query": {"type": "text", "label": "Search query", "required": True},
                "engine": {
                    "type": "select", "label": "Engine", "required": False,
                    "options": ["google", "bing", "duckduckgo"], "default": "google",
                },
                "count": {"type": "number", "label": "Result count", "required": False, "default": 10},
                "pool": {"type": "text", "label": "Device pool", "required": False, "default": "default"},
                "store_as": {"type": "text", "label": "Store results as variable", "required": False},
            },
            "execute": _serp_search,
        },
    }
