"""Device settings control: WiFi, brightness, airplane mode, etc."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class SettingsManager:
    """
    Control device settings.

    Usage:
        d.settings.wifi                     # True/False
        d.settings.wifi = False             # disable WiFi
        d.settings.brightness = 128         # 0-255
        d.settings.auto_brightness = True
        d.settings.airplane_mode = True
        d.settings.bluetooth = False
        d.settings.location = True
        d.settings.auto_rotate = False
        d.settings.set_volume("media", 10)
        d.settings.set_screen_timeout(120000)
        d.settings.set_locale("en-US")
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    # WiFi
    @property
    def wifi(self) -> bool:
        return self._conn.get_json("/settings/wifi").get("enabled", False)

    @wifi.setter
    def wifi(self, enabled: bool):
        self._conn.post_json("/settings/wifi", {"enabled": enabled})

    # Brightness
    @property
    def brightness(self) -> int:
        return self._conn.get_json("/settings/brightness").get("brightness", 0)

    @brightness.setter
    def brightness(self, level: int):
        self._conn.post_json("/settings/brightness", {"level": level})

    @property
    def auto_brightness(self) -> bool:
        return self._conn.get_json("/settings/brightness").get("auto", False)

    @auto_brightness.setter
    def auto_brightness(self, enabled: bool):
        self._conn.post_json("/settings/brightness", {"auto": enabled})

    # Airplane mode
    @property
    def airplane_mode(self) -> bool:
        return self._conn.get_json("/settings/airplane").get("enabled", False)

    @airplane_mode.setter
    def airplane_mode(self, enabled: bool):
        self._conn.post_json("/settings/airplane", {"enabled": enabled})

    # Volume
    @property
    def volume(self) -> dict:
        return self._conn.get_json("/settings/volume")

    def set_volume(self, stream: str = "media", level: int = 7) -> dict:
        """Set volume for a stream: media, ring, alarm, notification, system."""
        return self._conn.post_json("/settings/volume", {"stream": stream, "level": level})

    # Bluetooth
    @property
    def bluetooth(self) -> bool:
        return self._conn.get_json("/settings/bluetooth").get("enabled", False)

    @bluetooth.setter
    def bluetooth(self, enabled: bool):
        self._conn.post_json("/settings/bluetooth", {"enabled": enabled})

    # Location
    @property
    def location(self) -> bool:
        return self._conn.get_json("/settings/location").get("enabled", False)

    @location.setter
    def location(self, enabled: bool):
        self._conn.post_json("/settings/location", {"enabled": enabled})

    # Auto-rotate
    @property
    def auto_rotate(self) -> bool:
        return self._conn.get_json("/settings/auto_rotate").get("enabled", False)

    @auto_rotate.setter
    def auto_rotate(self, enabled: bool):
        self._conn.post_json("/settings/auto_rotate", {"enabled": enabled})

    # Locale
    def set_locale(self, locale: str) -> dict:
        """Set device locale (e.g. 'en-US', 'ja-JP')."""
        return self._conn.post_json("/settings/locale", {"locale": locale})

    # Screen timeout
    def set_screen_timeout(self, timeout_ms: int) -> dict:
        """Set screen timeout in milliseconds."""
        return self._conn.post_json("/settings/screen_timeout", {"timeout_ms": timeout_ms})
