"""Version-keyed UI adapters for ExpressVPN (``com.expressvpn.vpn``).

Each flow (``connect`` / ``disconnect`` / ``status``) is a list of :class:`VersionAdapter`, one
per version range, defining an *ordered list of steps*. The 12.x and 13.x connect adapters differ
by a whole step — 13.x added a per-connect VPN-consent dialog ("Allow") that 12.x never showed —
which is exactly why the unit is an adapter (add/remove/reorder steps), not just a selector map.

These selectors are hand-written against ExpressVPN's UI (plan 18 keeps record-and-replay out of
scope). ExpressVPN has no public automation intent, so it is the honest UI-automation case; an app
with a real intent API (WireGuard's ``SET_TUNNEL_UP``, OpenVPN-for-Android's API) wouldn't need
adapters at all — a driver could offer an intent backend instead.
"""
from devicekit_sdk.appdriver import (
    VersionAdapter, open_app, tap, tap_if_present, wait_for,
)

# On-screen labels the flows key off (the app's connected/disconnected state text).
CONNECTED = "Connected"
DISCONNECTED = "Not Connected"


def select_location(ctx):
    """Pick the requested exit location if the run passed one in ``ctx.vars['location']``; a no-op
    otherwise (connect to the current/last selection). Shared by the 12.x and 13.x connect
    adapters — the location bar → picker path is stable across those versions."""
    location = ctx.vars.get("location")
    if not location:
        return "no location requested — using current selection"
    ctx.tap_text("Selected Location")     # the location bar on the home screen opens the picker
    ctx.tap_text(location)                # tap the country/region row by its label
    return f"selected location '{location}'"


def status_probe(ctx):
    """Read the in-app connection state into ``ctx.vars`` (``connected`` bool + ``status`` string).
    This is the *app's* view — the egress verifier is what confirms the real exit country."""
    connected = ctx.exists(CONNECTED, timeout=3)
    ctx.vars["connected"] = connected
    ctx.vars["status"] = "connected" if connected else "disconnected"
    return f"app reports {'connected' if connected else 'disconnected'}"


ADAPTERS = {
    "connect": [
        VersionAdapter(">=12.0.0 <13.0.0", [
            open_app(),
            select_location,
            tap("Connect"),
            wait_for(CONNECTED),
        ], name="12.x"),
        VersionAdapter(">=13.0.0 <14.0.0", [
            open_app(),
            select_location,
            tap("Connect"),
            tap_if_present("Allow"),      # 13.x added a per-connect consent dialog — extra step
            wait_for(CONNECTED),
        ], name="13.x"),
    ],
    "disconnect": [
        VersionAdapter(">=12.0.0 <14.0.0", [
            open_app(),
            tap("Disconnect"),
            wait_for(DISCONNECTED),
        ], name="all"),
    ],
    "status": [
        VersionAdapter(">=12.0.0 <14.0.0", [
            open_app(),
            status_probe,
        ], name="all"),
    ],
}
