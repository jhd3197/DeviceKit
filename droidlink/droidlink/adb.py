"""ADB binary wrapper for device discovery and port forwarding."""

import subprocess
import shutil
from typing import List, Optional, Tuple


def _find_adb() -> str:
    """Find the adb binary on PATH."""
    adb = shutil.which("adb")
    if adb is None:
        raise FileNotFoundError(
            "adb not found on PATH. Install Android SDK Platform Tools."
        )
    return adb


def _run_adb(args: List[str], serial: Optional[str] = None, timeout: int = 10) -> Tuple[str, int]:
    """Run an adb command and return (stdout, returncode)."""
    cmd = [_find_adb()]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "adb command timed out", -1
    except Exception as e:
        return str(e), -1


def list_devices() -> List[dict]:
    """List connected ADB devices."""
    output, rc = _run_adb(["devices", "-l"])
    if rc != 0:
        return []
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            props = {}
            for part in parts[2:]:
                if ":" in part:
                    k, v = part.split(":", 1)
                    props[k] = v
            devices.append({
                "serial": serial,
                "model": props.get("model", ""),
                "device": props.get("device", ""),
                "transport_id": props.get("transport_id", ""),
            })
    return devices


def forward_port(serial: str, local_port: int, remote_port: int) -> bool:
    """Set up ADB port forwarding: localhost:local_port -> device:remote_port."""
    _, rc = _run_adb(
        ["forward", f"tcp:{local_port}", f"tcp:{remote_port}"],
        serial=serial,
    )
    return rc == 0


def remove_forward(local_port: int) -> bool:
    """Remove ADB port forwarding."""
    _, rc = _run_adb(["forward", "--remove", f"tcp:{local_port}"])
    return rc == 0


def list_forwards() -> List[dict]:
    """List all active ADB port forwards."""
    output, rc = _run_adb(["forward", "--list"])
    if rc != 0:
        return []
    forwards = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3:
            forwards.append({
                "serial": parts[0],
                "local": parts[1],
                "remote": parts[2],
            })
    return forwards


def push_file(serial: str, local_path: str, remote_path: str) -> bool:
    """Push a file to device via ADB."""
    _, rc = _run_adb(["push", local_path, remote_path], serial=serial, timeout=60)
    return rc == 0


def pull_file(serial: str, remote_path: str, local_path: str) -> bool:
    """Pull a file from device via ADB."""
    _, rc = _run_adb(["pull", remote_path, local_path], serial=serial, timeout=60)
    return rc == 0
