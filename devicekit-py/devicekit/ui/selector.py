"""UiSelector - chainable selector for finding UI elements."""

from typing import List, Optional, TYPE_CHECKING
from .element import UiElement
from ..exceptions import UiElementNotFoundError

if TYPE_CHECKING:
    from ..connection import Connection


class ScrollProxy:
    """Provides scroll methods on a selector: d(scrollable=True).scroll.to(text="Item")."""

    def __init__(self, conn: "Connection", selector: dict):
        self._conn = conn
        self._selector = selector

    def to(self, **kwargs) -> bool:
        """Scroll until an element matching kwargs is found. Returns True if found."""
        for _ in range(20):
            # Check if target exists
            data = self._conn.post_json("/ui/exists", kwargs)
            if data.get("exists"):
                return True
            # Scroll down
            scroll_params = {**self._selector, "direction": "down"}
            self._conn.post_json("/ui/scroll", scroll_params)
        return False

    def forward(self) -> dict:
        """Scroll forward (down)."""
        return self._conn.post_json("/ui/scroll", {**self._selector, "direction": "down"})

    def backward(self) -> dict:
        """Scroll backward (up)."""
        return self._conn.post_json("/ui/scroll", {**self._selector, "direction": "up"})

    def left(self) -> dict:
        """Scroll left."""
        return self._conn.post_json("/ui/scroll", {**self._selector, "direction": "left"})

    def right(self) -> dict:
        """Scroll right."""
        return self._conn.post_json("/ui/scroll", {**self._selector, "direction": "right"})


class UiSelector:
    """
    Chainable UI selector. Created via Device.__call__:
        d(text="Login").click()
        d(resourceId="com.app:id/btn", enabled=True).exists()
    """

    def __init__(self, conn: "Connection", **kwargs):
        self._conn = conn
        self._selector = {}

        # Map Python-style kwargs to API params
        key_map = {
            "text": "text",
            "resourceId": "resourceId",
            "resource_id": "resourceId",
            "className": "className",
            "class_name": "className",
            "description": "description",
            "content_desc": "description",
            "checkable": "checkable",
            "checked": "checked",
            "clickable": "clickable",
            "enabled": "enabled",
            "focusable": "focusable",
            "scrollable": "scrollable",
            "instance": "instance",
        }
        for k, v in kwargs.items():
            api_key = key_map.get(k, k)
            self._selector[api_key] = v

    def find(self) -> List[UiElement]:
        """Find all matching elements."""
        data = self._conn.post_json("/ui/find", self._selector)
        nodes = data.get("nodes", [])
        return [UiElement(self._conn, n) for n in nodes]

    def get(self) -> UiElement:
        """Get the first matching element. Raises UiElementNotFoundError if none."""
        elements = self.find()
        if not elements:
            raise UiElementNotFoundError(f"No element found for selector: {self._selector}")
        return elements[0]

    def click(self) -> dict:
        """Click the first matching element."""
        data = self._conn.post_json("/ui/click", self._selector)
        if not data.get("success"):
            raise UiElementNotFoundError(
                f"Click failed: {data.get('error', 'unknown')} (selector: {self._selector})"
            )
        return data

    def long_click(self, duration: int = 1000) -> dict:
        """Long click the first matching element."""
        return self._conn.post_json("/ui/long_click", {**self._selector, "duration": duration})

    def set_text(self, text: str) -> dict:
        """Set text on the first matching element."""
        return self._conn.post_json("/ui/set_text", {**self._selector, "text": text})

    def clear_text(self) -> dict:
        """Clear text from the first matching element."""
        return self._conn.post_json("/ui/clear_text", self._selector)

    def exists(self, timeout: int = 0) -> bool:
        """Check if a matching element exists. Optional timeout in seconds."""
        data = self._conn.post_json("/ui/exists", {**self._selector, "timeout": timeout})
        return data.get("exists", False)

    def wait(self, timeout: int = 10) -> Optional[UiElement]:
        """Wait for a matching element to appear. Returns element or None."""
        data = self._conn.post_json("/ui/wait", {**self._selector, "timeout": timeout},
                                    timeout=timeout + 5)
        if data.get("found") and "node" in data:
            return UiElement(self._conn, data["node"])
        return None

    @property
    def scroll(self) -> ScrollProxy:
        """Access scroll methods: d(scrollable=True).scroll.forward()"""
        return ScrollProxy(self._conn, self._selector)

    @property
    def count(self) -> int:
        """Count matching elements."""
        data = self._conn.post_json("/ui/find", self._selector)
        return data.get("count", 0)

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.exists()

    def __repr__(self) -> str:
        return f"UiSelector({self._selector})"
