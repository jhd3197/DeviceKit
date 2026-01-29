"""WiFi auto-discovery of devices on LAN via UDP broadcast."""

import json
import socket
import threading
from typing import List, Optional
from .types import DeviceInfo

DISCOVERY_PORT = 9801
DISCOVERY_PROBE = "DROIDLINK_DISCOVER"
DISCOVERY_RESPONSE_PREFIX = "DROIDLINK_DEVICE:"


def discover(timeout: float = 3.0, broadcast_address: str = "255.255.255.255") -> List[dict]:
    """
    Discover droidlink devices on the local network via UDP broadcast.

    Sends a broadcast probe and collects responses from devices running
    the DeviceKit agent with the discovery service enabled.

    Args:
        timeout: How long to wait for responses (seconds).
        broadcast_address: Broadcast address to use.

    Returns:
        List of discovered device dicts with keys:
        model, manufacturer, sdk, android_version, device, ip, port, agent, version
    """
    devices = []
    seen_ips = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    try:
        # Send discovery probe
        message = DISCOVERY_PROBE.encode("utf-8")
        sock.sendto(message, (broadcast_address, DISCOVERY_PORT))

        # Collect responses
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                response = data.decode("utf-8").strip()
                if response.startswith(DISCOVERY_RESPONSE_PREFIX):
                    json_str = response[len(DISCOVERY_RESPONSE_PREFIX):]
                    device_info = json.loads(json_str)
                    ip = device_info.get("ip", addr[0])
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        device_info["ip"] = ip
                        devices.append(device_info)
            except socket.timeout:
                break
            except Exception:
                continue
    finally:
        sock.close()

    return devices


def discover_and_connect(timeout: float = 3.0) -> List:
    """
    Discover devices and return connected Device instances.

    Returns:
        List of connected Device objects.
    """
    from .connection import connect_wifi
    from .device import Device

    found = discover(timeout=timeout)
    devices = []
    for info in found:
        ip = info.get("ip")
        port = info.get("port", 9800)
        if ip and ip != "0.0.0.0":
            try:
                conn = connect_wifi(ip, port)
                devices.append(Device(conn))
            except Exception:
                pass
    return devices
