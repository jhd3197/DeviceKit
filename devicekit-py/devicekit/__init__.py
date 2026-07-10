"""
devicekit - Python bridge for Android device control via DeviceKit agent.

Usage:
    import devicekit

    d = devicekit.connect()                     # auto-detect USB device
    d = devicekit.connect("SERIAL")             # specific device
    d = devicekit.connect_wifi("192.168.1.5")   # WiFi direct

    d(text="Login").click()
    d.screenshot("screen.png")
    d.shell("ls /sdcard")
    d.toast("Hello from Python!")
    d.events.stream().on("notification", print).start()
    d.settings.wifi = False
"""

from .device import Device
from .connection import connect_usb, Connection, AGENT_PORT
from .connection import connect_wifi as _connect_wifi_conn
from .adb import list_devices as _list_adb_devices
from .discovery import discover, discover_and_connect
from .exceptions import (
    DeviceKitError,
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
    "connect_all",
    "devices",
    "discover",
    "discover_and_connect",
    "Device",
    "Connection",
    "AGENT_PORT",
    # Exceptions
    "DeviceKitError",
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
    conn = _connect_wifi_conn(host, port)
    return Device(conn)


def connect_all() -> list:
    """
    Connect to all available devices (USB via ADB + WiFi via discovery).

    Returns:
        List of Device instances.
    """
    devices_list = []

    # USB devices via ADB
    from . import adb
    for dev in adb.list_devices():
        try:
            serial = dev["serial"]
            # Use unique port per device to avoid conflicts
            port = AGENT_PORT + len(devices_list)
            conn = connect_usb(serial=serial, local_port=port)
            devices_list.append(Device(conn))
        except Exception:
            pass

    # WiFi devices via discovery
    try:
        wifi_devices = discover_and_connect(timeout=2.0)
        # Avoid duplicates (same device over USB and WiFi)
        usb_serials = {d.serial for d in devices_list if d.serial}
        for wd in wifi_devices:
            if wd.serial not in usb_serials:
                devices_list.append(wd)
    except Exception:
        pass

    return devices_list


def devices() -> list:
    """List connected ADB devices."""
    return _list_adb_devices()
