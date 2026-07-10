"""UiElement - represents a found UI node on the device."""

from typing import Optional, TYPE_CHECKING
from ..types import UiNode

if TYPE_CHECKING:
    from ..connection import Connection


class UiElement:
    """Represents a UI element found on the device. Wraps a UiNode with actions."""

    def __init__(self, conn: "Connection", node_data: dict):
        self._conn = conn
        self._data = node_data
        self.node = UiNode.from_dict(node_data)

    @property
    def text(self) -> Optional[str]:
        return self.node.text

    @property
    def resource_id(self) -> Optional[str]:
        return self.node.resource_id

    @property
    def class_name(self) -> Optional[str]:
        return self.node.class_name

    @property
    def content_desc(self) -> Optional[str]:
        return self.node.content_desc

    @property
    def bounds(self) -> dict:
        return {
            "left": self.node.bounds_left,
            "top": self.node.bounds_top,
            "right": self.node.bounds_right,
            "bottom": self.node.bounds_bottom,
        }

    @property
    def center(self) -> tuple:
        return (self.node.center_x, self.node.center_y)

    def click(self) -> dict:
        """Click this element."""
        x, y = self.center
        return self._conn.post_json("/input/tap", {"x": x, "y": y})

    def long_click(self, duration: int = 1000) -> dict:
        """Long click this element."""
        x, y = self.center
        return self._conn.post_json("/input/long_tap", {"x": x, "y": y, "duration": duration})

    def set_text(self, text: str) -> dict:
        """Set text on this element (tap to focus, clear, type)."""
        selector = self._build_selector()
        selector["text_to_set"] = text
        return self._conn.post_json("/ui/set_text", {**selector, "text": text})

    def clear_text(self) -> dict:
        """Clear text from this element."""
        selector = self._build_selector()
        return self._conn.post_json("/ui/clear_text", selector)

    def _build_selector(self) -> dict:
        """Build a selector dict that can re-find this element."""
        s = {}
        if self.node.resource_id:
            s["resourceId"] = self.node.resource_id
        elif self.node.text:
            s["text"] = self.node.text
        elif self.node.content_desc:
            s["description"] = self.node.content_desc
        return s

    @property
    def info(self) -> dict:
        """Return the raw node data."""
        return self._data

    def __repr__(self) -> str:
        parts = []
        if self.node.resource_id:
            parts.append(f"id={self.node.resource_id!r}")
        if self.node.text:
            parts.append(f"text={self.node.text!r}")
        if self.node.class_name:
            parts.append(f"class={self.node.class_name!r}")
        return f"UiElement({', '.join(parts)})"
