# devicekit

Android device control and test automation in Python — the client library of the
[DeviceKit](https://github.com/jhd3197/DeviceKit) platform. Connect to phones over
USB or WiFi, drive the UI, run shell commands, manage files and apps, read metrics
and notifications, and plug straight into pytest for device testing in CI.

Devices run the lightweight DeviceKit agent app (an HTTP server on the phone);
this library talks to it directly — over USB via ADB port forwarding, or over
WiFi with UDP auto-discovery. No backend server required.

## Install

```bash
pip install devicekit
```

## Quick Start

```python
import devicekit

# Connect via USB (auto-detect)
d = devicekit.connect()

# Connect to a specific device
d = devicekit.connect("EMULATOR5554")

# Connect via WiFi (no ADB needed)
d = devicekit.connect_wifi("192.168.1.5")

# Device info
print(d.info)       # model, SDK, screen size
print(d.battery)    # level, charging, temperature

# UI Automation
d(text="Login").click()
d(resourceId="com.app:id/input").set_text("hello")
d(className="android.widget.EditText", instance=2).clear_text()
d(scrollable=True).scroll.to(text="Bottom Item")
if d(text="Error").exists(timeout=3):
    print("Error dialog appeared")

# Screenshots
d.screenshot("screen.png")

# Shell commands
result = d.shell("whoami")
print(result.output)

# File management
files = d.files.list("/sdcard/DCIM/")
d.files.push("./config.json", "/sdcard/config.json")
d.files.pull("/sdcard/photo.jpg", "./photo.jpg")

# App management
d.app.launch("com.android.chrome")
apps = d.app.list(filter="user")
results = d.app.search("chrome")

# Notifications
notifications = d.notifications.list()

# Device metrics
metrics = d.metrics.snapshot()
print(f"CPU: {metrics.cpu_percent}%, RAM: {metrics.ram_used_mb}MB")

# Clipboard
d.clipboard.set("copied text")
print(d.clipboard.get())
```

## CLI

```bash
devicekit devices              # list connected devices
devicekit ping                 # check agent connectivity
devicekit info                 # show device info
devicekit screenshot -o s.png  # take screenshot
devicekit shell "ls /sdcard"   # run shell command
devicekit apps                 # list user apps
devicekit notifications        # list notifications
devicekit metrics              # show device metrics
```

## pytest plugin

The package ships a pytest plugin with `device` and `device_pool` fixtures:

```python
def test_login_flow(device):
    device.app.launch("com.example.app")
    device(text="Login").click()
    assert device(text="Welcome").exists(timeout=5)
```

```bash
pytest tests/ --device <SERIAL>              # USB device
pytest tests/ --device-wifi 192.168.1.5      # WiFi device
pytest tests/ --devicekit-url http://ci:5050 # report results to a DeviceKit backend
```

With `--devicekit-url`, test results, build lifecycle, and failure screenshots are
reported to the DeviceKit dashboard automatically.

## Requirements

- Python 3.8+
- Android device with the DeviceKit agent app installed and running
- ADB (for USB connections) or WiFi connectivity

## Part of DeviceKit

This library is the programmatic entry point to the larger
[DeviceKit platform](https://github.com/jhd3197/DeviceKit): a fleet dashboard with
real-time streaming, a visual automation editor with AI generation and self-healing,
visual regression testing, fleet queries, and failure debug bundles.

## License

MIT
