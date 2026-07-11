"""Lifecycle hooks for devicekit-explorer (best-effort)."""
import devicekit_sdk

SLUG = "devicekit-explorer"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info("File Explorer installed. Open a device and use the Files tab, or the Files page.")


def on_uninstall(client, purge=False):
    log.info(f"File Explorer uninstalled (purge={purge}).")
