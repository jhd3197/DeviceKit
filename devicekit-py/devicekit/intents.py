"""Intent firing: broadcast, start activity, open URL."""

from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class IntentManager:
    """
    Fire Android intents from Python.

    Usage:
        d.intent.broadcast("com.example.ACTION", extras={"key": "value"})
        d.intent.start("android.settings.WIFI_SETTINGS")
        d.intent.open_url("https://google.com")
        d.intent.start_service("com.app/.MyService")
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def broadcast(self, action: str, extras: Optional[Dict[str, Any]] = None,
                  package: Optional[str] = None, data: Optional[str] = None) -> dict:
        """Send a broadcast intent."""
        body = {"action": action}
        if extras:
            body["extras"] = extras
        if package:
            body["package"] = package
        if data:
            body["data"] = data
        return self._conn.post_json("/intent/broadcast", body)

    def start(self, action: str = "", component: str = "",
              extras: Optional[Dict[str, Any]] = None,
              data: Optional[str] = None,
              category: Optional[str] = None,
              package: Optional[str] = None) -> dict:
        """Start an activity via intent."""
        body = {}
        if action:
            body["action"] = action
        if component:
            body["component"] = component
        if extras:
            body["extras"] = extras
        if data:
            body["data"] = data
        if category:
            body["category"] = category
        if package:
            body["package"] = package
        return self._conn.post_json("/intent/start", body)

    def start_service(self, action: str = "", component: str = "",
                      extras: Optional[Dict[str, Any]] = None) -> dict:
        """Start a service via intent."""
        body = {}
        if action:
            body["action"] = action
        if component:
            body["component"] = component
        if extras:
            body["extras"] = extras
        return self._conn.post_json("/intent/service", body)

    def open_url(self, url: str) -> dict:
        """Open a URL in the default browser."""
        return self._conn.post_json("/intent/open_url", {"url": url})
