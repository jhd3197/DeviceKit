# CI/CD Setup for DeviceKit Device Tests

Run automated Android device tests in CI using GitHub Actions self-hosted runners with USB-connected devices.

## Self-Hosted Runner Requirements

- **OS**: Linux or macOS (Windows possible with Git Bash)
- **ADB**: Android Debug Bridge installed and in PATH
- **USB Devices**: One or more Android devices connected via USB with USB debugging enabled
- **Python 3.11+**
- **Network**: Runner must reach the DeviceKit backend (default `localhost:5050`)

### Verify ADB setup

```bash
adb devices -l
# Should show your connected device(s)
```

## GitHub Secrets

Configure these in **Settings > Secrets and variables > Actions**:

| Secret | Required | Description |
|--------|----------|-------------|
| `DEVICEKIT_API_KEY` | Yes | API key for the DeviceKit backend |
| `DEVICEKIT_URL` | No | Backend URL (default: `http://127.0.0.1:5050`) |

### Repository Variables (optional)

| Variable | Description |
|----------|-------------|
| `DEVICE_SERIAL` | ADB serial of the target device |
| `DEVICE_WIFI` | WiFi IP of the target device |

## WiFi Device Configuration

For devices connected over WiFi instead of USB:

1. Ensure the device and runner are on the same network
2. Set the `DEVICE_WIFI` repository variable to the device IP (e.g., `192.168.1.100`)
3. Or pass `--device-wifi=IP` in the pytest command

```yaml
- name: Run tests (WiFi)
  run: |
    pytest tests/ \
      --device-wifi=${{ vars.DEVICE_WIFI }} \
      --devicekit-url=${{ env.DEVICEKIT_URL }}
```

## Example conftest.py with Device Locking

When multiple CI jobs share the same device pool, use device locking to prevent collisions:

```python
import os
import pytest
import requests

DEVICEKIT_URL = os.environ.get("DEVICEKIT_URL", "http://127.0.0.1:5050")
API_KEY = os.environ.get("DEVICEKIT_API_KEY", "")
OWNER = os.environ.get("GITHUB_RUN_ID", "ci-runner")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def locked_device():
    """Acquire an available device with a lock for the test session."""
    # Get available (unlocked) devices
    resp = requests.get(
        f"{DEVICEKIT_URL}/devices/available",
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    devices = resp.json().get("devices", [])
    if not devices:
        pytest.skip("No available devices")

    device_id = devices[0].get("serial") or devices[0].get("device_id")

    # Lock the device
    lock_resp = requests.post(
        f"{DEVICEKIT_URL}/devices/{device_id}/lock",
        headers=HEADERS,
        json={"owner": OWNER, "timeout": 600},
        timeout=10,
    )
    lock_resp.raise_for_status()

    yield device_id

    # Unlock on teardown
    requests.post(
        f"{DEVICEKIT_URL}/devices/{device_id}/unlock",
        headers=HEADERS,
        json={"owner": OWNER},
        timeout=10,
    )
```

Usage in tests:

```python
import devicekit

def test_login_flow(locked_device):
    d = devicekit.connect(locked_device)
    d.app.launch("com.example.app")
    d(text="Login").click()
    assert d(text="Welcome").exists()
```

## Troubleshooting

### ADB device not detected

```bash
# Check USB connection
lsusb | grep -i android
# Restart ADB server
adb kill-server && adb start-server
adb devices
```

### Backend not reachable

```bash
# Check if backend is running
curl -s http://127.0.0.1:5050/health
# Check firewall
sudo ufw status
```

### Device locked by stale CI run

Locks auto-expire after their timeout (default 5 minutes). To force-unlock:

```bash
curl -X POST http://127.0.0.1:5050/devices/DEVICE_ID/unlock \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"owner": "force"}'
```

### Tests pass locally but fail in CI

- Verify the device screen is on: `adb shell input keyevent 26`
- Check device orientation: `adb shell settings get system accelerometer_rotation`
- Ensure sufficient storage: `adb shell df /data`
- Check agent is running: `adb shell ps | grep devicekit`

### pytest plugin not found

```bash
# Verify installation
pip show devicekit
# Check entry point registered
pip install devicekit
pytest --co  # should not show "no tests" if plugin loaded
```
