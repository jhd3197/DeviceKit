# droidlink — driving a fleet from Python

[`droidlink`](https://pypi.org/project/droidlink/) is DeviceKit's Python client library. It talks
**directly to a device's on-device agent HTTP server** (the same agent from
[Fleet Contract](FLEET_CONTRACT.md)) — over USB via `adb forward`, or over WiFi via UDP discovery —
so it needs **no backend** for device control. It only touches the DeviceKit backend to report CI
test results.

This is the **fleet-usage** guide: connect to a DeviceKit-managed device, script actions and tests,
and wire it into CI. droidlink lives in its [own repo](https://github.com/jhd3197/droidlink) and has
a full API reference there — **this doc links out rather than duplicating it**, to avoid two sources
of truth that drift. It kept the `droidlink` name (not `devicekit`) for the reason in
[ADR 0004](adr/0004-droidlink-name-on-pypi.md).

- **Repo:** <https://github.com/jhd3197/droidlink>
- **PyPI:** `pip install droidlink` (Python 3.8+)
- **Requirement:** the device must be running the DeviceKit agent app (its HTTP server, port 9800).

---

## Connect

```python
import droidlink

d = droidlink.connect()                    # USB — first ADB device, auto adb-forward
d = droidlink.connect("R9TT311P25N")       # USB — a specific serial
d = droidlink.connect_wifi("192.168.1.5")  # WiFi — no ADB, direct to the device
devices = droidlink.connect_all()          # every USB + WiFi device, each on its own port
```

- **USB** (`connect`): picks the first ADB device (or the serial you pass), sets up
  `adb forward tcp:9800 tcp:9800` for you, and pings the agent. Raises if the agent app isn't
  running.
- **WiFi** (`connect_wifi`): connects straight to `http://<ip>:9800`. Devices are auto-discoverable
  via `droidlink.discover()` (UDP broadcast on 9801).

> **Auth caveat.** If the agent enforces a token, the top-level `connect()` / `connect_wifi()`
> wrappers do **not** forward an `api_key`. Use the transport layer directly:
> `droidlink.connect_usb(serial, api_key="…")` or `droidlink.Connection(base_url, api_key="…")` —
> the key is sent as the agent's `X-Agent-Token` header. (This is separate from the backend's
> `X-API-Key`.)

## Control the device

A connected `Device` exposes managers plus convenience methods. The canonical quickstart:

```python
d = droidlink.connect("R9TT311P25N")

print(d.info)                              # model / Android version / display
print(d.battery)                           # level / temperature / charging

d(text="Login").click()                    # uiautomator2-style UI selectors
d.screenshot("screen.png")
print(d.shell("whoami").output)
d.files.push("./config.json", "/sdcard/config.json")
d.app.launch("com.android.chrome")
```

The manager surface (full reference in the [droidlink repo](https://github.com/jhd3197/droidlink)):
`files`, `shell`, `input`, `screen`, `app`, `clipboard`, `notifications`, `metrics`, `ui` (the
`d(...)` selector), `events`, `gestures`, `streaming`, `logcat`, `intent`, `settings`, `contacts`,
`sms`. UI selectors accept `text`, `resourceId`, `className`, `description`, and more, with
`.click()`, `.set_text()`, `.exists(timeout=)`, `.wait(timeout=)`, and `.scroll`.

## "Run an automation" from Python

droidlink drives the device **directly** — you write the flow in Python rather than running a stored
DeviceKit automation. A login flow, for example:

```python
def login(d, user, pw):
    d.app.launch("com.example.app")
    d(text="Email").set_text(user)
    d(text="Password").set_text(pw)
    d(text="Sign in").click()
    assert d(text="Welcome").exists(timeout=10), "login failed"

d = droidlink.connect()
login(d, "user@test.com", "hunter2")
```

Fan the same flow across the fleet with `connect_all()`:

```python
for d in droidlink.connect_all():
    login(d, "user@test.com", "hunter2")
```

For repeatable macros, `d.gestures` can record taps/swipes on the device and replay them by name.

## The CLI

`pip install droidlink` also installs a `droidlink` CLI. Global flags `-s/--serial` (USB) and
`-w/--wifi <ip>` (WiFi) pick the target:

| Command | Does |
| --- | --- |
| `droidlink devices` | List connected ADB devices. |
| `droidlink ping` | Check agent connectivity. |
| `droidlink info` | Model / Android version / display. |
| `droidlink screenshot [-o FILE]` | Save a screenshot. |
| `droidlink shell "<cmd>"` | Run a shell command (exits with its code). |
| `droidlink apps [-f all|user|system]` | List installed apps. |
| `droidlink notifications` | Recent notifications. |
| `droidlink metrics` | CPU / RAM / battery / temp / network. |
| `droidlink files list\|search\|upload\|pull …` | File operations with progress. |

## Use it in CI

droidlink ships a **pytest plugin** (no separate package — it's in the same install). Two
session-scoped fixtures, and reporting straight into the DeviceKit backend's pipeline dashboard:

```python
def test_login_flow(device):            # `device` fixture = a connected droidlink Device
    device.app.launch("com.example.app")
    device(text="Login").click()
    assert device(text="Welcome").exists(timeout=5)
```

```bash
pytest tests/ --device R9TT311P25N                    # USB serial
pytest tests/ --device-wifi 192.168.1.5               # WiFi
pytest tests/ --devicekit-url http://ci:5050 \
              --devicekit-api-key "$KEY"              # report results to the backend
```

| Fixture / option | Meaning |
| --- | --- |
| `device` | One connected `Device` (from `--device` / `--device-wifi`, else auto-detect). |
| `device_pool` | All connected devices (`connect_all()`), for parallel/sharded runs. |
| `--device` / `--device-wifi` | Target serial (USB) or IP (WiFi). Env: `DROIDLINK_DEVICE(_WIFI)`. |
| `--devicekit-url` / `--devicekit-api-key` | Backend URL + key for reporting. Env: `DEVICEKIT_URL` / `DEVICEKIT_API_KEY`. |
| `--no-report` | Disable backend reporting. |
| `--screenshot-on-failure` | Capture a screenshot on failure (default on). |

The plugin opens a build at session start (`POST /pipeline/builds`), reports each test
(`POST /pipeline/builds/<id>/tests`, with a failure screenshot from the `device` fixture), and
closes the build at session end — all failing silently so reporting never breaks a run. The full CI
walkthrough (self-hosted runners, secrets, device locking) is in [CI/CD Setup](ci-setup.md).

---

## Ports & where the backend fits

| Port | Used for |
| --- | --- |
| **9800** | The device's agent HTTP server — what droidlink drives. |
| **9801** | UDP discovery (WiFi auto-detect). |
| **5050** | The DeviceKit backend — **only** for pytest result reporting. |

droidlink controls devices with **no backend involved**; the backend enters only when you report CI
results. For how the agent's server and the backend relate, see [Architecture](ARCHITECTURE.md); for
the agent uplink protocol, [Fleet Contract](FLEET_CONTRACT.md). For the complete droidlink API
(every manager and method), go to the [droidlink repo](https://github.com/jhd3197/droidlink).
