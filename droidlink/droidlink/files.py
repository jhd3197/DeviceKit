"""File management: list, read, write, push, pull, delete."""

from pathlib import Path
from typing import List, Optional, TYPE_CHECKING
from .types import FileInfo, StorageVolume

if TYPE_CHECKING:
    from .connection import Connection


class FileManager:
    """File operations on the device."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def list(self, path: str = "/sdcard") -> List[FileInfo]:
        """List files and directories at path."""
        data = self._conn.get_json("/files/list", params={"path": path})
        return [FileInfo.from_dict(item) for item in data.get("items", [])]

    def read(self, remote_path: str) -> bytes:
        """Read a file's contents as bytes."""
        return self._conn.get_bytes("/files/read", params={"path": remote_path}, timeout=30)

    def read_text(self, remote_path: str, encoding: str = "utf-8") -> str:
        """Read a file as text."""
        return self.read(remote_path).decode(encoding)

    def write(self, remote_path: str, content: str) -> dict:
        """Write text content to a file on device."""
        return self._conn.post_json("/files/write", {"path": remote_path, "content": content})

    def mkdir(self, remote_path: str) -> dict:
        """Create a directory (and parents) on device."""
        return self._conn.post_json("/files/mkdir", {"path": remote_path})

    def delete(self, remote_path: str) -> dict:
        """Delete a file or directory on device."""
        return self._conn.post_json("/files/delete", {"path": remote_path})

    def rename(self, from_path: str, to_path: str) -> dict:
        """Rename/move a file on device."""
        return self._conn.post_json("/files/rename", {"from": from_path, "to": to_path})

    def push(self, local_path: str, remote_path: str) -> bool:
        """Push a local file to device via ADB."""
        from . import adb
        serial = self._conn.serial
        if serial is None:
            raise RuntimeError("push() requires ADB connection (not WiFi). Use write() instead.")
        return adb.push_file(serial, local_path, remote_path)

    def pull(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from device via ADB."""
        from . import adb
        serial = self._conn.serial
        if serial is None:
            # Fallback: download via HTTP
            data = self.read(remote_path)
            Path(local_path).write_bytes(data)
            return True
        return adb.pull_file(serial, remote_path, local_path)

    def storage(self) -> List[StorageVolume]:
        """Get storage volume info."""
        data = self._conn.get_json("/info/storage")
        volumes = []
        for v in data.get("volumes", []):
            volumes.append(StorageVolume(
                name=v.get("name", ""),
                path=v.get("path", ""),
                total_bytes=v.get("total_bytes", 0),
                free_bytes=v.get("free_bytes", 0),
                available_bytes=v.get("available_bytes", 0),
            ))
        return volumes
