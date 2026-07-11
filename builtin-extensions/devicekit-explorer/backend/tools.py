"""AI tools for devicekit-explorer — bound namespaced ``devicekit_explorer__*``.

``device_id`` is injected by the host and hidden from the model. ``delete_file`` is a write
tool, so it is always routed through the confirmation gate (plan 13); the readers run free.
"""
import requests

import devicekit_sdk
from devicekit_sdk import require_permission

SLUG = "devicekit-explorer"
READ_TEXT_MAX = 40000


def _agent_base(device_id):
    host = devicekit_sdk.get_host()
    if host is None or not hasattr(host, "find_agent_device"):
        return None
    try:
        agent = host.find_agent_device(device_id)
    except Exception:
        return None
    if not agent or not agent.get("online"):
        return None
    info = agent.get("info") or {}
    ip = info.get("ip")
    port = info.get("agent_port", 9800)
    return f"http://{ip}:{port}" if ip else None


def register(ai):
    @ai.tool(is_write=False)
    def list_files(path: str = "/sdcard", device_id: str = "") -> str:
        """List files and directories at a path on the device."""
        require_permission(SLUG, "filesystem")
        base = _agent_base(device_id)
        if not base:
            return "Agent not available for this device."
        r = requests.get(f"{base}/files/list", params={"path": path}, timeout=8)
        items = (r.json() or {}).get("items", []) if r.ok else []
        if not items:
            return f"(empty or unreadable: {path})"
        return "\n".join(
            f"{'d' if i.get('is_dir') else '-'} {i.get('size', 0):>10} {i.get('name')}"
            for i in items)

    @ai.tool(is_write=False)
    def read_text_file(path: str, device_id: str = "") -> str:
        """Read a text file from the device (size-capped)."""
        require_permission(SLUG, "filesystem")
        base = _agent_base(device_id)
        if not base:
            return "Agent not available for this device."
        r = requests.get(f"{base}/files/read", params={"path": path}, timeout=15)
        if not r.ok:
            return f"Could not read {path} ({r.status_code})."
        return r.text[:READ_TEXT_MAX]

    @ai.tool
    def delete_file(path: str, device_id: str = "") -> str:
        """Delete a file or directory on the device (recursive). Destructive."""
        require_permission(SLUG, "filesystem")
        base = _agent_base(device_id)
        if not base:
            return "Agent not available for this device."
        r = requests.post(f"{base}/files/delete", json={"path": path}, timeout=15)
        ok = r.ok and (r.json() or {}).get("success", True) if r.content else r.ok
        return f"Deleted {path}" if ok else f"Delete failed for {path}"
