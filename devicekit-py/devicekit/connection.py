"""Connection management: ADB discovery, port forwarding, HTTP session."""

import os
import requests
from typing import Callable, Optional
from . import adb
from .exceptions import DeviceNotFoundError, ConnectionError, AgentNotRunningError

AGENT_PORT = 9800
DEFAULT_TIMEOUT = 10


class Connection:
    """Manages the connection to a device's agent HTTP server."""

    def __init__(self, base_url: str, serial: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.serial = serial
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if api_key:
            self.session.headers["X-Agent-Token"] = api_key
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

    def get_bytes_streamed(self, path: str, params: Optional[dict] = None,
                           timeout: Optional[int] = None,
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> bytes:
        """Download bytes with optional progress reporting."""
        url = f"{self.base_url}{path}"
        resp = self.session.get(
            url, params=params, timeout=timeout or self._timeout, stream=True
        )
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        chunks = []
        downloaded = 0
        for chunk in resp.iter_content(chunk_size=8192):
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)
        return b"".join(chunks)

    def post_file(self, path: str, file_path: str,
                  params: Optional[dict] = None,
                  progress_callback: Optional[Callable[[int, int], None]] = None,
                  timeout: Optional[int] = None) -> requests.Response:
        """Upload a file via multipart POST with optional progress reporting."""
        url = f"{self.base_url}{path}"
        file_size = os.path.getsize(file_path)

        if progress_callback:
            reader = _ProgressReader(file_path, progress_callback, file_size)
            # Use requests-toolbelt-style monitored upload
            files = {"file": (os.path.basename(file_path), reader, "application/octet-stream")}
        else:
            files = {"file": (os.path.basename(file_path), open(file_path, "rb"), "application/octet-stream")}

        # Don't send Content-Type: application/json for multipart
        headers = {k: v for k, v in self.session.headers.items() if k.lower() != "content-type"}
        resp = self.session.post(
            url, files=files, params=params, timeout=timeout or 120, headers=headers
        )
        resp.raise_for_status()
        return resp

    def ping(self) -> bool:
        try:
            data = self.get_json("/ping", timeout=3)
            return data.get("status") == "ok"
        except Exception:
            return False

    def close(self):
        self.session.close()


def connect_usb(serial: Optional[str] = None, local_port: int = AGENT_PORT, api_key: Optional[str] = None) -> Connection:
    """Connect to a USB-attached device via ADB port forwarding."""
    if serial is None:
        devices = adb.list_devices()
        if not devices:
            raise DeviceNotFoundError("No ADB devices found. Connect a device via USB.")
        serial = devices[0]["serial"]

    # Set up port forwarding
    if not adb.forward_port(serial, local_port, AGENT_PORT):
        raise ConnectionError(f"Failed to set up port forwarding for {serial}")

    conn = Connection(f"http://127.0.0.1:{local_port}", serial=serial, api_key=api_key)

    if not conn.ping():
        raise AgentNotRunningError(
            f"Agent not responding on {serial}. "
            "Make sure the DeviceKit agent app is running."
        )

    return conn


class _ProgressReader:
    """File-like wrapper that reports read progress via callback."""

    def __init__(self, file_path: str, callback: Callable[[int, int], None], total: int):
        self._file = open(file_path, "rb")
        self._callback = callback
        self._total = total
        self._read = 0

    def read(self, size=-1):
        data = self._file.read(size)
        if data:
            self._read += len(data)
            self._callback(self._read, self._total)
        return data

    def __len__(self):
        return self._total

    def seek(self, offset, whence=0):
        self._file.seek(offset, whence)
        if whence == 0:
            self._read = offset

    def tell(self):
        return self._file.tell()


def connect_wifi(host: str, port: int = AGENT_PORT, api_key: Optional[str] = None) -> Connection:
    """Connect directly to a device over WiFi (no ADB needed)."""
    conn = Connection(f"http://{host}:{port}", api_key=api_key)

    if not conn.ping():
        raise AgentNotRunningError(
            f"Agent not responding at {host}:{port}. "
            "Make sure the DeviceKit agent app is running and the device is on the same network."
        )

    return conn
