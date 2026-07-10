"""Device class - main interface for controlling an Android device."""

from pathlib import Path
from typing import Optional

from .connection import Connection
from .types import DeviceInfo, BatteryInfo, KeyboardState, ShellResult
from .input import InputManager
from .screen import ScreenManager
from .shell import ShellManager
from .files import FileManager
from .apps import AppManager
from .clipboard import ClipboardManager
from .notifications import NotificationManager
from .metrics import MetricsManager
from .events import EventManager
from .gestures import GestureManager
from .streaming import ScreenStream
from .logcat import LogcatManager
from .intents import IntentManager
from .settings import SettingsManager
from .contacts import ContactsManager, SmsManager
from .ui.selector import UiSelector


class StateProxy:
    """Access device state: d.state.keyboard, etc."""

    def __init__(self, conn: Connection):
        self._conn = conn

    @property
    def keyboard(self) -> KeyboardState:
        data = self._conn.get_json("/state/keyboard")
        return KeyboardState.from_dict(data)

    @property
    def full(self) -> dict:
        return self._conn.get_json("/state")


class Device:
    """
    Main interface for controlling an Android device.

    Usage:
        d = Device(connection)
        d.info                         # DeviceInfo
        d.battery                      # BatteryInfo
        d.screenshot("screen.png")     # take screenshot
        d(text="Login").click()        # UI automation
        d.shell("ls /sdcard")          # shell commands
        d.files.list("/sdcard")        # file management
        d.app.launch("com.chrome")     # app management
        d.notifications.list()         # notifications
        d.metrics.snapshot()           # device metrics
        d.events.stream()              # real-time SSE events
        d.gestures.replay("name")      # gesture replay
        d.screen_stream(fps=5)         # MJPEG mirroring
        d.logcat.dump()                # logcat
        d.intent.broadcast(...)        # fire intents
        d.settings.wifi = False        # settings control
        d.contacts.list()              # contacts
        d.sms.list()                   # SMS
        d.toast("Hello!")              # show toast
    """

    def __init__(self, conn: Connection):
        self._conn = conn
        self._input = InputManager(conn)
        self._screen = ScreenManager(conn)
        self._shell = ShellManager(conn)
        self._files = FileManager(conn)
        self._app = AppManager(conn)
        self._clipboard = ClipboardManager(conn)
        self._notifications = NotificationManager(conn)
        self._metrics = MetricsManager(conn)
        self._events = EventManager(conn)
        self._gestures = GestureManager(conn)
        self._logcat = LogcatManager(conn)
        self._intent = IntentManager(conn)
        self._settings = SettingsManager(conn)
        self._contacts = ContactsManager(conn)
        self._sms = SmsManager(conn)
        self._state = StateProxy(conn)

    # -- Properties --

    @property
    def info(self) -> DeviceInfo:
        """Get device info (model, SDK, screen size, etc.)."""
        data = self._conn.get_json("/info")
        return DeviceInfo.from_dict(data)

    @property
    def battery(self) -> BatteryInfo:
        """Get battery info."""
        data = self._conn.get_json("/info/battery")
        return BatteryInfo.from_dict(data)

    @property
    def serial(self) -> Optional[str]:
        """ADB serial of connected device."""
        return self._conn.serial

    # -- Managers --

    @property
    def files(self) -> FileManager:
        return self._files

    @property
    def app(self) -> AppManager:
        return self._app

    @property
    def clipboard(self) -> ClipboardManager:
        return self._clipboard

    @property
    def notifications(self) -> NotificationManager:
        return self._notifications

    @property
    def metrics(self) -> MetricsManager:
        return self._metrics

    @property
    def events(self) -> EventManager:
        """Access real-time event streaming."""
        return self._events

    @property
    def gestures(self) -> GestureManager:
        """Gesture recording and replay."""
        return self._gestures

    @property
    def logcat(self) -> LogcatManager:
        """Logcat access."""
        return self._logcat

    @property
    def intent(self) -> IntentManager:
        """Intent firing."""
        return self._intent

    @property
    def settings(self) -> SettingsManager:
        """Device settings control."""
        return self._settings

    @property
    def contacts(self) -> ContactsManager:
        """Contacts access."""
        return self._contacts

    @property
    def sms(self) -> SmsManager:
        """SMS access."""
        return self._sms

    @property
    def state(self) -> StateProxy:
        return self._state

    # -- Direct methods --

    def screenshot(self, filename: Optional[str] = None) -> bytes:
        """Take a screenshot. Returns PNG bytes. Optionally saves to file."""
        return self._screen.screenshot(filename)

    def shell(self, command: str, timeout: int = 30) -> ShellResult:
        """Execute a shell command on the device."""
        return self._shell(command, timeout)

    def click(self, x: int, y: int) -> dict:
        """Tap at screen coordinates."""
        return self._input.tap(x, y)

    def long_click(self, x: int, y: int, duration: int = 1000) -> dict:
        """Long tap at screen coordinates."""
        return self._input.long_tap(x, y, duration)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> dict:
        """Swipe from (x1,y1) to (x2,y2)."""
        return self._input.swipe(x1, y1, x2, y2, duration)

    def press(self, key: str) -> dict:
        """Press a named key: home, back, menu, enter, etc."""
        return self._input.press(key)

    def send_keys(self, text: str) -> dict:
        """Type text string."""
        return self._input.text(text)

    def wake(self) -> dict:
        """Wake the screen."""
        return self._screen.wake()

    def sleep(self) -> dict:
        """Put the screen to sleep."""
        return self._screen.sleep()

    @property
    def rotation(self) -> int:
        """Current screen rotation."""
        return self._screen.rotation

    def ping(self) -> bool:
        """Check if agent is responding."""
        return self._conn.ping()

    def toast(self, message: str, duration: str = "short") -> dict:
        """Show a toast message on the device screen."""
        return self._conn.post_json("/toast", {"message": message, "duration": duration})

    def open_url(self, url: str) -> dict:
        """Open a URL in the default browser."""
        return self._intent.open_url(url)

    def screen_stream(self, fps: int = 5, quality: int = 50) -> ScreenStream:
        """
        Create an MJPEG screen stream.

        Usage:
            stream = d.screen_stream(fps=5)
            stream.on_frame(lambda data, i: save(data))
            stream.start()

            # Or iterate:
            for frame in d.screen_stream(fps=2):
                process(frame)
        """
        return ScreenStream(self._conn, fps=fps, quality=quality)

    # -- UI Selector (uiautomator2-style) --

    def __call__(self, **kwargs) -> UiSelector:
        """
        Create a UI selector. Examples:
            d(text="Login").click()
            d(resourceId="com.app:id/btn").set_text("hello")
            d(className="android.widget.EditText", instance=2).clear_text()
            d(scrollable=True).scroll.to(text="Bottom")
        """
        return UiSelector(self._conn, **kwargs)

    def dump_hierarchy(self) -> dict:
        """Dump the full UI hierarchy as a dict."""
        return self._conn.post_json("/ui/dump")

    def __repr__(self) -> str:
        serial = self._conn.serial or "wifi"
        return f"Device({serial}, {self._conn.base_url})"
