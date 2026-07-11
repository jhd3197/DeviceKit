"""Lifecycle hooks for devicekit-vpn (best-effort; failures are logged and swallowed)."""
import devicekit_sdk

SLUG = "devicekit-vpn"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info(
        "VPN (ExpressVPN driver) installed. Next: upload the ExpressVPN APK to the extension's "
        "apk_b64 config (with apk_sha256/apk_version to pin it), set allowed_countries + "
        "preferred_location, then POST /ext/devicekit-vpn/devices/<id>/provision per device.")


def on_uninstall(client, purge=False):
    # No live device state to tear down (no persistent adb forwards); the provisioning ledger is
    # dropped by the platform on purge.
    log.info(f"VPN driver uninstalled (purge={purge}).")
