"""Data types for droidlink."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DeviceInfo:
    model: str = ""
    manufacturer: str = ""
    brand: str = ""
    device: str = ""
    product: str = ""
    sdk: int = 0
    android_version: str = ""
    serial: str = ""
    display_width: int = 0
    display_height: int = 0
    display_density: float = 0.0
    display_dpi: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        display = data.get("display", {})
        return cls(
            model=data.get("model", ""),
            manufacturer=data.get("manufacturer", ""),
            brand=data.get("brand", ""),
            device=data.get("device", ""),
            product=data.get("product", ""),
            sdk=data.get("sdk", 0),
            android_version=data.get("android_version", ""),
            serial=data.get("serial", ""),
            display_width=display.get("width", 0),
            display_height=display.get("height", 0),
            display_density=display.get("density", 0.0),
            display_dpi=display.get("dpi", 0),
        )


@dataclass
class BatteryInfo:
    level: int = 0
    temperature: float = 0.0
    is_charging: bool = False
    status: str = "unknown"
    health: str = "unknown"
    plugged: str = "none"

    @classmethod
    def from_dict(cls, data: dict) -> "BatteryInfo":
        return cls(
            level=data.get("level", 0),
            temperature=data.get("temperature", 0.0),
            is_charging=data.get("is_charging", False),
            status=data.get("status", "unknown"),
            health=data.get("health", "unknown"),
            plugged=data.get("plugged", "none"),
        )


@dataclass
class StorageVolume:
    name: str = ""
    path: str = ""
    total_bytes: int = 0
    free_bytes: int = 0
    available_bytes: int = 0

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024**3)

    @property
    def free_gb(self) -> float:
        return self.free_bytes / (1024**3)


@dataclass
class FileInfo:
    name: str = ""
    path: str = ""
    is_dir: bool = False
    size: int = 0
    modified: int = 0
    readable: bool = True
    writable: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "FileInfo":
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            is_dir=data.get("is_dir", False),
            size=data.get("size", 0),
            modified=data.get("modified", 0),
            readable=data.get("readable", True),
            writable=data.get("writable", True),
        )


@dataclass
class AppInfo:
    package: str = ""
    label: str = ""
    version_name: str = ""
    version_code: int = 0
    is_system: bool = False
    enabled: bool = True
    target_sdk: int = 0
    min_sdk: int = 0
    apk_size: int = 0
    source_dir: str = ""
    activities: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    first_install: int = 0
    last_update: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "AppInfo":
        return cls(
            package=data.get("package", ""),
            label=data.get("label", ""),
            version_name=data.get("version_name", ""),
            version_code=data.get("version_code", 0),
            is_system=data.get("is_system", False),
            enabled=data.get("enabled", True),
            target_sdk=data.get("target_sdk", 0),
            min_sdk=data.get("min_sdk", 0),
            apk_size=data.get("apk_size", 0),
            source_dir=data.get("source_dir", ""),
            activities=data.get("activities", []),
            permissions=data.get("permissions", []),
            first_install=data.get("first_install", 0),
            last_update=data.get("last_update", 0),
        )


@dataclass
class ShellResult:
    output: str = ""
    exit_code: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class NotificationInfo:
    package: str = ""
    title: Optional[str] = None
    text: Optional[str] = None
    timestamp: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationInfo":
        return cls(
            package=data.get("package", ""),
            title=data.get("title"),
            text=data.get("text"),
            timestamp=data.get("timestamp", 0),
        )


@dataclass
class MetricsSnapshot:
    cpu_percent: float = 0.0
    ram_used_mb: int = 0
    ram_total_mb: int = 0
    battery_level: int = 0
    battery_temperature: float = 0.0
    is_charging: bool = False
    network_type: str = "unknown"
    network_rx_rate: int = 0
    network_tx_rate: int = 0
    timestamp: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "MetricsSnapshot":
        return cls(
            cpu_percent=data.get("cpu_percent", 0.0),
            ram_used_mb=data.get("ram_used_mb", 0),
            ram_total_mb=data.get("ram_total_mb", 0),
            battery_level=data.get("battery_level", 0),
            battery_temperature=data.get("battery_temperature", 0.0),
            is_charging=data.get("is_charging", False),
            network_type=data.get("network_type", "unknown"),
            network_rx_rate=data.get("network_rx_rate", 0),
            network_tx_rate=data.get("network_tx_rate", 0),
            timestamp=data.get("timestamp", 0),
        )


@dataclass
class KeyboardState:
    visible: bool = False
    focused_field_id: Optional[str] = None
    focused_field_type: Optional[str] = None
    focused_field_text: Optional[str] = None
    focused_package: Optional[str] = None
    focused_class: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "KeyboardState":
        return cls(
            visible=data.get("visible", False),
            focused_field_id=data.get("focused_field_id"),
            focused_field_type=data.get("focused_field_type"),
            focused_field_text=data.get("focused_field_text"),
            focused_package=data.get("focused_package"),
            focused_class=data.get("focused_class"),
        )


@dataclass
class UiNode:
    class_name: Optional[str] = None
    resource_id: Optional[str] = None
    text: Optional[str] = None
    content_desc: Optional[str] = None
    package: Optional[str] = None
    checkable: bool = False
    checked: bool = False
    clickable: bool = False
    enabled: bool = True
    focusable: bool = False
    focused: bool = False
    scrollable: bool = False
    long_clickable: bool = False
    selected: bool = False
    editable: bool = False
    visible: bool = True
    bounds_left: int = 0
    bounds_top: int = 0
    bounds_right: int = 0
    bounds_bottom: int = 0
    children: List["UiNode"] = field(default_factory=list)

    @property
    def center_x(self) -> int:
        return (self.bounds_left + self.bounds_right) // 2

    @property
    def center_y(self) -> int:
        return (self.bounds_top + self.bounds_bottom) // 2

    @classmethod
    def from_dict(cls, data: dict) -> "UiNode":
        bounds = data.get("bounds", {})
        children_data = data.get("children", [])
        return cls(
            class_name=data.get("class"),
            resource_id=data.get("resource_id"),
            text=data.get("text"),
            content_desc=data.get("content_desc"),
            package=data.get("package"),
            checkable=data.get("checkable", False),
            checked=data.get("checked", False),
            clickable=data.get("clickable", False),
            enabled=data.get("enabled", True),
            focusable=data.get("focusable", False),
            focused=data.get("focused", False),
            scrollable=data.get("scrollable", False),
            long_clickable=data.get("long_clickable", False),
            selected=data.get("selected", False),
            editable=data.get("editable", False),
            visible=data.get("visible", True),
            bounds_left=bounds.get("left", 0),
            bounds_top=bounds.get("top", 0),
            bounds_right=bounds.get("right", 0),
            bounds_bottom=bounds.get("bottom", 0),
            children=[UiNode.from_dict(c) for c in children_data],
        )
