"""Lifecycle hooks for devicekit-browser (best-effort; failures are logged and swallowed)."""
import devicekit_sdk

SLUG = "devicekit-browser"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info("Browser (CDP driver) installed. Create a pool via POST /ext/devicekit-browser/pools "
             "to route across devices, or drive one device at /devices/<id>/goto.")


def on_uninstall(client, purge=False):
    # Best-effort: tear down any live adb forwards so we don't leak them.
    try:
        from . import sessions
        for sess in sessions.list_sessions():
            sessions.close_session(sess["device_id"])
    except Exception as e:
        log.warning(f"Session teardown on uninstall failed: {e}")
    log.info(f"Browser uninstalled (purge={purge}).")
