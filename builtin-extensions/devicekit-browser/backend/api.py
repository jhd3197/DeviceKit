"""Sibling-facing API surface for devicekit-browser (plan 17).

Curated, in-process callables other extensions reach via ``sdk.extension("devicekit-browser")``
— pool-routed fetch, nothing more (not the whole blueprint). The host gates every call on this
extension being *active* (``ExtensionUnavailable`` otherwise), so a disabled browser cleanly
degrades a dependent like ``devicekit-serp`` instead of failing deep inside a search.

This is the same navigate→read-content path as ``POST /pools/<name>/fetch`` with the same
round-robin + busy-skip failover, exposed as a plain function that returns structured data
(``device_id`` separated from the HTML) so a caller doesn't have to parse a display string.
"""
from . import cdp, sessions, pools
from .cdp import CDPError
from .pools import PoolError

SLUG = "devicekit-browser"

_VALID_FORMATS = ("html", "text", "title", "url")


def fetch(pool="default", url=None, fmt="html"):
    """Navigate a device from ``pool`` (round-robin across the fleet, skipping busy/cooling
    devices, transparent failover) to ``url`` and return ``{device_id, url, <fmt>}`` where
    ``<fmt>`` is one of ``html``/``text``/``title``/``url`` (default ``html``).

    Raises :class:`PoolError` when the pool is missing or has no available device, and
    :class:`CDPError` when every candidate device failed to serve the page.
    """
    if not url:
        raise ValueError("url is required")
    fmt = fmt if fmt in _VALID_FORMATS else "html"
    pool_row = pools.get_pool(pool)
    if not pool_row:
        raise PoolError(
            f"no such pool '{pool}'. Create one first: POST /ext/devicekit-browser/pools")

    excluded = set()
    members = pools.resolve_members(pool_row)
    last_err = None
    for _ in range(max(1, len(members))):
        device_id = pools.pick_device(pool_row, exclude=excluded)
        try:
            port, tid = sessions.session_context(device_id)
            cdp.navigate(port, tid, url, timeout=sessions.cdp_timeout())
            body = cdp.content(port, tid, fmt=fmt, timeout=sessions.cdp_timeout())
            return {"device_id": device_id, "url": url, fmt: body}
        except CDPError as e:
            last_err = e
            pools.mark_unhealthy(device_id)
            excluded.add(device_id)
    raise CDPError(f"fetch failed across pool '{pool}': {last_err}")


def register(api):
    """Register the sibling-callable surface (plan 17 provider seam)."""
    api.method(fetch)
