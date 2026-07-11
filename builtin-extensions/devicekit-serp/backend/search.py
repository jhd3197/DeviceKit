"""The one function this extension exists to provide: ``search()`` over a real device's Chrome.

Every device touch goes through ``sdk.extension("devicekit-browser").fetch(...)`` — SERP owns no
device code (that is the whole point of plan 17's dependency mechanism: without
``requires_extensions`` this would have to re-implement CDP-over-adb). The browser extension picks
a device from the pool round-robin, navigates, and returns the HTML plus which ``device_id`` served
it; the engine adapter parses results out of that HTML.
"""
import devicekit_sdk

from . import engines

SLUG = "devicekit-serp"
BROWSER_SLUG = "devicekit-browser"
log = devicekit_sdk.logger(SLUG)

MAX_COUNT = 50


def search(query, engine="google", count=10, pool="default"):
    """Run ``query`` on ``engine`` through the ``devicekit-browser`` device ``pool`` and return
    ``{query, engine, device_id, count, results: [{title, url, snippet}]}``.

    On a parse failure (the engine's results container wasn't found — DOM drift or a block page)
    the return carries an explicit ``error`` and an ``html_sample`` for debugging, with
    ``results: []`` — never a silent empty list. Propagates
    :class:`devicekit_sdk.ExtensionUnavailable` when the browser extension is missing/disabled,
    and the browser's ``PoolError``/``CDPError`` when no device could serve the page — those are
    the caller's to surface.
    """
    if not query:
        raise ValueError("query is required")
    try:
        count = max(1, min(int(count), MAX_COUNT))
    except (TypeError, ValueError):
        count = 10

    adapter = engines.get_adapter(engine)          # raises ValueError on an unknown engine
    url = engines.build_url(engine, query, count)

    browser = devicekit_sdk.extension(BROWSER_SLUG)
    fetched = browser.fetch(pool=pool, url=url, fmt="html")
    html = fetched.get("html") or ""
    device_id = fetched.get("device_id")

    try:
        results = adapter["parse"](html, count)
    except engines.ParseError as e:
        log.warning(f"SERP parse failure on {engine} (served by {device_id}): {e}")
        return {
            "query": query, "engine": engine.lower(), "device_id": device_id,
            "count": 0, "results": [],
            "error": f"could not parse {engine} results ({e}); the result DOM may have changed "
                     f"or the request was blocked",
            "html_sample": html[:800],
        }

    return {
        "query": query, "engine": engine.lower(), "device_id": device_id,
        "count": len(results), "results": results,
    }
