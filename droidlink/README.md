# droidlink

Python bridge for Android device control via the DeviceKit agent app.

## Install

```bash
pip install -e .
```

## Quick Start

```python
import droidlink

# Connect via USB (auto-detect)
d = droidlink.connect()

# Connect to specific device
d = droidlink.connect("EMULATOR5554")

# Connect via WiFi (no ADB needed)
d = droidlink.connect_wifi("192.168.1.5")

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

# Notifications (unique to droidlink)
notifications = d.notifications.list()

# Device metrics (unique to droidlink)
metrics = d.metrics.snapshot()
print(f"CPU: {metrics.cpu_percent}%, RAM: {metrics.ram_used_mb}MB")

# Clipboard
d.clipboard.set("copied text")
print(d.clipboard.get())
```

## CLI

```bash
droidlink devices              # list connected devices
droidlink ping                 # check agent connectivity
droidlink info                 # show device info
droidlink screenshot -o s.png  # take screenshot
droidlink shell "ls /sdcard"   # run shell command
droidlink apps                 # list user apps
droidlink notifications        # list notifications
droidlink metrics              # show device metrics
```

## Requirements

- Python 3.8+
- Android device with DeviceKit agent app installed and running
- ADB (for USB connections) or WiFi connectivity
