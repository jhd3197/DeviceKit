"""App management: list, launch, stop, install, uninstall, search."""

from typing import List, Optional, TYPE_CHECKING
from .types import AppInfo

if TYPE_CHECKING:
    from .connection import Connection


class AppManager:
    """App management operations."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def list(self, filter: str = "all") -> List[AppInfo]:
        """List installed apps. filter: 'all', 'user', 'system'."""
        data = self._conn.get_json("/app/list", params={"filter": filter})
        return [AppInfo.from_dict(a) for a in data.get("apps", [])]

    def info(self, package: str) -> AppInfo:
        """Get detailed info for a package."""
        data = self._conn.get_json("/app/info", params={"package": package})
        return AppInfo.from_dict(data)

    def current(self) -> dict:
        """Get the current foreground app package and activity."""
        return self._conn.get_json("/app/current")

    def search(self, query: str) -> List[AppInfo]:
        """Search installed apps by name or package."""
        data = self._conn.get_json("/app/search", params={"q": query})
        return [AppInfo.from_dict(a) for a in data.get("results", [])]

    def launch(self, package: str) -> dict:
        """Launch an app by package name."""
        return self._conn.post_json("/app/launch", {"package": package})

    def stop(self, package: str) -> dict:
        """Force stop an app."""
        return self._conn.post_json("/app/stop", {"package": package})

    def install(self, path: str) -> dict:
        """Install an APK. Path should be on the device.
        For local APKs, push first with d.files.push()."""
        return self._conn.post_json("/app/install", {"path": path})

    def uninstall(self, package: str) -> dict:
        """Uninstall an app."""
        return self._conn.post_json("/app/uninstall", {"package": package})
