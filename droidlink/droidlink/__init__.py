"""
droidlink - Python bridge for Android device control via DeviceKit agent.

Usage:
    import droidlink

    d = droidlink.connect()                     # auto-detect USB device
    d = droidlink.connect("SERIAL")             # specific device
    d = droidlink.connect_wifi("192.168.1.5")   # WiFi direct

    d(text="Login").click()
    d.screenshot("screen.png")
    d.shell("ls /sdcard")
"""

from .device import Device
from .connection import connect_usb, connect_wifi, Connection, AGENT_PORT
from .adb import list_devices as _list_adb_devices
from .exceptions import (
    DroidLinkError,
    DeviceNotFoundError,
    ConnectionError,
    AdbError,
    UiElementNotFoundError,
    AgentNotRunningError,
    ShellCommandError,
)
from .types import (
    DeviceInfo,
    BatteryInfo,
    StorageVolume,
    FileInfo,
    AppInfo,
    ShellResult,
    NotificationInfo,
    MetricsSnapshot,
    KeyboardState,
    UiNode,
)

__version__ = "0.1.0"
__all__ = [
    "connect",
    "connect_wifi",
    "devices",
    "Device",
    "Connection",
    "AGENT_PORT",
    # Exceptions
    "DroidLinkError",
    "DeviceNotFoundError",
    "ConnectionError",
    "AdbError",
    "UiElementNotFoundError",
    "AgentNotRunningError",
    "ShellCommandError",
    # Types
    "DeviceInfo",
    "BatteryInfo",
    "StorageVolume",
    "FileInfo",
    "AppInfo",
    "ShellResult",
    "NotificationInfo",
    "MetricsSnapshot",
    "KeyboardState",
    "UiNode",
]


def connect(serial: str = None, local_port: int = AGENT_PORT) -> Device:
    """
    Connect to a device via ADB (USB).

    Args:
        serial: ADB serial number. Auto-detects if None.
        local_port: Local port for ADB forwarding (default 9800).

    Returns:
        Device instance ready for use.
    """
    conn = connect_usb(serial=serial, local_port=local_port)
    return Device(conn)


def connect_wifi(host: str, port: int = AGENT_PORT) -> Device:
    """
    Connect to a device directly over WiFi (no ADB needed).

    Args:
        host: Device IP address.
        port: Agent HTTP server port (default 9800).

    Returns:
        Device instance ready for use.
    """
    from .connection import connect_wifi as _connect_wifi
    conn = _connect_wifi(host, port)
    return Device(conn)


def devices() -> list:
    """List connected ADB devices."""
    return _list_adb_devices()
