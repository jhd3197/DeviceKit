"""AI tools for devicekit-vpn — bound namespaced ``devicekit_vpn__*`` into every per-device
Prompture ToolRegistry. The host binds the conversation's ``device_id`` and hides it from the
model. Write tools (connect/disconnect/provision/reprovision) are **always** routed through the
confirmation gate (plan 13) — third-party code never gets autonomous network control; read tools
(status/verify_egress) run free. ``connect`` validates the country before doing anything, so even
the AI can't route to a non-approved exit."""
import devicekit_sdk

from . import driver

SLUG = "devicekit-vpn"


def register(ai):
    @ai.tool
    def connect(location: str = "", device_id: str = "") -> str:
        """Connect this device's VPN to a location (country code or name; blank uses the preferred
        location). The country is validated against the allowed-countries list before connecting."""
        result = driver.connect(device_id, location=location or None)
        return f"Connected (v{result['version']}, {result['adapter']} adapter, location='{result['location']}')"

    @ai.tool
    def disconnect(device_id: str = "") -> str:
        """Disconnect this device's VPN."""
        result = driver.disconnect(device_id)
        return f"Disconnected (v{result['version']})"

    @ai.tool
    def provision(device_id: str = "") -> str:
        """Install the pinned VPN app onto this device (verifies the sha256 pin first)."""
        rec = driver.provision(device_id)
        return f"Provisioned {rec['package']} v{rec['version_name']} ({rec['status']})"

    @ai.tool(is_write=False)
    def status(device_id: str = "") -> str:
        """Report whether this device's VPN app shows connected, and its installed version."""
        return str(driver.status(device_id))

    @ai.tool(is_write=False)
    def verify_egress(device_id: str = "") -> str:
        """Confirm the device's real exit country via a device-side geo-IP check (the app UI can't
        reveal a wrong-country connection). Returns the exit country and whether it is approved."""
        return str(driver.verify_egress(device_id))
