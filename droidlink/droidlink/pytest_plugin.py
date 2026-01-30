"""
pytest-droidlink: pytest plugin for DeviceKit integration.

Provides device fixtures, screenshot-on-failure capture, and automatic
result reporting to the DeviceKit backend pipeline.

Usage:
    pytest tests/ --device=SERIAL --devicekit-url=http://localhost:5050
    pytest tests/ --device-wifi=192.168.1.5
    pytest tests/ --no-report  # disable backend reporting
"""

import base64
import os
import time

import pytest
import requests


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    group = parser.getgroup("droidlink", "DroidLink device testing")
    group.addoption(
        "--device",
        action="store",
        default=os.environ.get("DROIDLINK_DEVICE"),
        help="Device serial (USB) or IP:port (WiFi)",
    )
    group.addoption(
        "--device-wifi",
        action="store",
        default=os.environ.get("DROIDLINK_DEVICE_WIFI"),
        help="WiFi device IP shorthand",
    )
    group.addoption(
        "--devicekit-url",
        action="store",
        default=os.environ.get("DEVICEKIT_URL", "http://127.0.0.1:5050"),
        help="DeviceKit backend URL (default: http://127.0.0.1:5050)",
    )
    group.addoption(
        "--devicekit-api-key",
        action="store",
        default=os.environ.get("DEVICEKIT_API_KEY", ""),
        help="API key for DeviceKit backend",
    )
    group.addoption(
        "--no-report",
        action="store_true",
        default=False,
        help="Disable backend reporting",
    )
    group.addoption(
        "--screenshot-on-failure",
        action="store_true",
        default=True,
        help="Capture screenshot on test failure (default: True)",
    )


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class DroidLinkReporter:
    """Reports test results to the DeviceKit pipeline API."""

    def __init__(self, base_url, api_key=""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.build_id = None
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        if api_key:
            self.session.headers["X-API-Key"] = api_key

    def _post(self, path, json_data):
        try:
            return self.session.post(
                f"{self.base_url}{path}", json=json_data, timeout=10
            )
        except Exception:
            return None

    def _put(self, path, json_data):
        try:
            return self.session.put(
                f"{self.base_url}{path}", json=json_data, timeout=10
            )
        except Exception:
            return None

    def start_build(self, session):
        """Create a new build at session start."""
        items = session.items if hasattr(session, "items") else []
        total_tests = len(items) if items else 0
        resp = self._post("/pipeline/builds", {
            "title": f"pytest run ({total_tests} tests)",
            "source": "pytest-droidlink",
            "total_tests": total_tests,
        })
        if resp and resp.ok:
            data = resp.json()
            self.build_id = data.get("id")
            # Transition to running
            self._put(f"/pipeline/builds/{self.build_id}/status", {
                "status": "running",
            })

    def report_test(self, nodeid, status, duration_ms, device="",
                    error_message="", traceback_str="", screenshot_b64=None):
        """Report a single test result."""
        if not self.build_id:
            return
        self._post(f"/pipeline/builds/{self.build_id}/tests", {
            "name": nodeid,
            "status": status,
            "duration": duration_ms,
            "device": device,
            "error_message": error_message,
            "traceback": traceback_str,
            "screenshot_b64": screenshot_b64,
        })

    def finish_build(self, exitstatus):
        """Finalize the build."""
        if not self.build_id:
            return
        status = "completed" if exitstatus == 0 else "failed"
        self._put(f"/pipeline/builds/{self.build_id}/status", {
            "status": status,
        })

    def capture_screenshot(self, item):
        """Capture screenshot from device fixture, return base64 string or None."""
        try:
            device = item.funcargs.get("device")
            if device is None:
                return None
            png_bytes = device.screenshot()
            if png_bytes:
                return base64.b64encode(png_bytes).decode("ascii")
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def device(request):
    """
    Session-scoped droidlink Device.

    Connects via --device (serial/USB), --device-wifi (WiFi IP), or auto-detect.
    """
    import droidlink

    serial = request.config.getoption("--device")
    wifi = request.config.getoption("--device-wifi")

    if wifi:
        return droidlink.connect_wifi(wifi)
    if serial:
        # If serial contains ":" it's a WiFi address
        if ":" in serial and not serial.startswith("emulator"):
            host, _, port = serial.partition(":")
            return droidlink.connect_wifi(host, int(port) if port else 9800)
        return droidlink.connect(serial)
    # Auto-detect
    return droidlink.connect()


@pytest.fixture(scope="session")
def device_pool():
    """Session-scoped list of all available devices via droidlink.connect_all()."""
    import droidlink
    return droidlink.connect_all()


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Create reporter if reporting is enabled."""
    if config.getoption("--no-report", default=False):
        config._droidlink_reporter = None
        return
    url = config.getoption("--devicekit-url", default="http://127.0.0.1:5050")
    api_key = config.getoption("--devicekit-api-key", default="")
    config._droidlink_reporter = DroidLinkReporter(url, api_key)


def pytest_sessionstart(session):
    """Start a build in the backend."""
    reporter = getattr(session.config, "_droidlink_reporter", None)
    if reporter:
        reporter.start_build(session)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Report each test result with status/duration/error/screenshot."""
    outcome = yield
    report = outcome.get_result()

    # Only report the "call" phase (not setup/teardown)
    if report.when != "call":
        return

    reporter = getattr(item.config, "_droidlink_reporter", None)
    if not reporter:
        return

    # Map pytest outcome to our status
    if report.passed:
        status = "pass"
    elif report.failed:
        status = "fail"
    elif report.skipped:
        status = "skip"
    else:
        status = "error"

    duration_ms = int(report.duration * 1000)

    error_message = ""
    traceback_str = ""
    screenshot_b64 = None

    if report.failed:
        error_message = str(report.longrepr).split("\n")[0] if report.longrepr else ""
        traceback_str = str(report.longrepr) if report.longrepr else ""

        # Screenshot on failure
        if item.config.getoption("--screenshot-on-failure", default=True):
            screenshot_b64 = reporter.capture_screenshot(item)

    # Determine device identifier
    device_str = ""
    try:
        dev = item.funcargs.get("device")
        if dev and hasattr(dev, "serial"):
            device_str = dev.serial or ""
    except Exception:
        pass

    reporter.report_test(
        nodeid=item.nodeid,
        status=status,
        duration_ms=duration_ms,
        device=device_str,
        error_message=error_message,
        traceback_str=traceback_str,
        screenshot_b64=screenshot_b64,
    )


def pytest_sessionfinish(session, exitstatus):
    """Finalize the build."""
    reporter = getattr(session.config, "_droidlink_reporter", None)
    if reporter:
        reporter.finish_build(exitstatus)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print build ID and backend URL link."""
    reporter = getattr(config, "_droidlink_reporter", None)
    if reporter and reporter.build_id:
        url = reporter.base_url
        build_id = reporter.build_id
        terminalreporter.write_sep("=", "DroidLink Pipeline Report")
        terminalreporter.write_line(f"Build ID: {build_id}")
        terminalreporter.write_line(f"View results: {url}/pipeline/builds/{build_id}")
