"""Lifecycle hooks — convenience, not correctness (failures are logged and swallowed by the
host). ``client`` is the DeviceKit Client composite; uninstall also receives ``purge``."""
import devicekit_sdk

SLUG = "devicekit-webhook-notify"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info("Webhook Notifier installed. Set 'webhook_url' in the extension config to enable delivery.")


def on_uninstall(client, purge=False):
    log.info(f"Webhook Notifier uninstalled (purge={purge}).")
