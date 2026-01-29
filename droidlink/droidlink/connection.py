"""Connection management: ADB discovery, port forwarding, HTTP session."""

import requests
from typing import Optional
from . import adb
from .exceptions import DeviceNotFoundError, ConnectionError, AgentNotRunningError

AGENT_PORT = 9800
DEFAULT_TIMEOUT = 10


class Connection:
    """Manages the connection to a device's agent HTTP server."""

    def __init__(self, base_url: str, serial: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.serial = serial
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._timeout = DEFAULT_TIMEOUT

    def get(self, path: str, params: Optional[dict] = None,
            timeout: Optional[int] = None, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self.session.get(
            url, params=params, timeout=timeout or self._timeout, **kwargs
        )

    def post(self, path: str, json: Optional[dict] = None,
             timeout: Optional[int] = None, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self.session.post(
            url, json=json, timeout=timeout or self._timeout, **kwargs
        )

    def get_json(self, path: str, params: Optional[dict] = None,
                 timeout: Optional[int] = None) -> dict:
        resp = self.get(path, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, path: str, json: Optional[dict] = None,
                  timeout: Optional[int] = None) -> dict:
        resp = self.post(path, json=json, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def get_bytes(self, path: str, params: Optional[dict] = None,
                  timeout: Optional[int] = None) -> bytes:
        resp = self.get(path, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.content

    def ping(self) -> bool:
        try:
            data = self.get_json("/ping", timeout=3)
            return data.get("status") == "ok"
        except Exception:
            return False

    def close(self):
        self.session.close()


def connect_usb(serial: Optional[str] = None, local_port: int = AGENT_PORT) -> Connection:
    """Connect to a USB-attached device via ADB port forwarding."""
    if serial is None:
        devices = adb.list_devices()
        if not devices:
            raise DeviceNotFoundError("No ADB devices found. Connect a device via USB.")
        serial = devices[0]["serial"]

    # Set up port forwarding
    if not adb.forward_port(serial, local_port, AGENT_PORT):
        raise ConnectionError(f"Failed to set up port forwarding for {serial}")

    conn = Connection(f"http://127.0.0.1:{local_port}", serial=serial)

    if not conn.ping():
        raise AgentNotRunningError(
            f"Agent not responding on {serial}. "
            "Make sure the DeviceKit agent app is running."
        )

    return conn


def connect_wifi(host: str, port: int = AGENT_PORT) -> Connection:
    """Connect directly to a device over WiFi (no ADB needed)."""
    conn = Connection(f"http://{host}:{port}")

    if not conn.ping():
        raise AgentNotRunningError(
            f"Agent not responding at {host}:{port}. "
            "Make sure the DeviceKit agent app is running and the device is on the same network."
        )

    return conn
