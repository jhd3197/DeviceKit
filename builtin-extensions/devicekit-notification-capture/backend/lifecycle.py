"""Lifecycle hooks for devicekit-notification-capture (best-effort)."""
import devicekit_sdk

SLUG = "devicekit-notification-capture"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info("Notification Capture installed. It polls devices whose agent advertises the "
             "notification listener; configure a package allowlist / regex filter and set "
             "forward_to_bus to route matches to your notification channels.")


def on_uninstall(client, purge=False):
    log.info(f"Notification Capture uninstalled (purge={purge}).")
