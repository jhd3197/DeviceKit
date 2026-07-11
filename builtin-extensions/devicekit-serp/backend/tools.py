"""AI tool for devicekit-serp — bound namespaced ``devicekit_serp__search`` into every
per-device Prompture ToolRegistry.

It is a **read** tool (``is_write=False``): SERP mutates nothing on the device itself. The gated
write is the underlying ``devicekit-browser`` fetch, and it is gated *there*, once — double-gating
would just nag. This is a fleet-level tool (no ``device_id`` parameter): the browser pool picks
which device serves the query, so the model addresses "the fleet", not one device.
"""
import devicekit_sdk

from .search import search as run_search

SLUG = "devicekit-serp"


def register(ai):
    @ai.tool(is_write=False)
    def search(query: str, engine: str = "google", count: int = 10, pool: str = "default") -> str:
        """Search the web using a real device's Chrome (via the devicekit-browser pool) and
        return ranked results as a numbered list of "title — url". Engines: google, bing,
        duckduckgo. Uses residential device IPs and rotates across the fleet; no API key."""
        try:
            res = run_search(query, engine=engine, count=count, pool=pool)
        except devicekit_sdk.ExtensionUnavailable as e:
            return f"Search unavailable: {e}. Install and enable devicekit-browser, then create a device pool."
        except Exception as e:
            return f"Search failed: {e}"
        if res.get("error"):
            return f"[{res['engine']}] {res['error']}"
        results = res.get("results") or []
        if not results:
            return f"[{res['engine']} via {res.get('device_id')}] no results for '{query}'."
        lines = [f"{i + 1}. {r['title']} — {r['url']}" for i, r in enumerate(results)]
        return (f"[{res['engine']} via {res.get('device_id')}] {len(results)} results for "
                f"'{query}':\n" + "\n".join(lines))
