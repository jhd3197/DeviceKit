# Getting Started

From nothing to a running automation on a real device. This walks the manual (dev) path — the
one you'll use while building — and points at Docker where it's the faster start. If you want to
understand the pieces first, read [Architecture](ARCHITECTURE.md).

**You'll need:**

- **Python 3.11+** (the backend)
- **Node 18+** (the frontend)
- **ADB** (Android Debug Bridge) on your `PATH` — the backend shells out to it
- An **Android device** (Android 7+, USB debugging enabled) *or* the DeviceKit agent APK
- *(optional)* a Prompture provider API key if you want the AI features — see [AI Agent](ai-agent.md)

---

## 1. Clone and configure

```bash
git clone https://github.com/jhd3197/DeviceKit.git
cd DeviceKit
cp .env.example .env
```

`.env` is optional in dev — **auth is disabled by default** (`API_KEY` empty), so you can run the
whole stack without setting anything. The vars worth knowing:

| Var | Why you'd set it |
| --- | --- |
| `API_KEY` | Turn on API-key auth (dashboard + droidlink must then send `X-API-Key`). Leave empty for dev. |
| `AGENT_TOKENS` | Turn on agent-token auth for `/agent-device/*`. Leave empty for dev. |
| `DEVICEKIT_DATABASE_URL` | Point at Postgres to scale out. Defaults to an embedded SQLite file at `backend/devicekit.db`. |
| `PROMPTURE_DEFAULT_MODEL` + provider key | Enable AI automation/agents (e.g. `ANTHROPIC_API_KEY`). Without one, AI routes return a clear error. |

The full list is in the [root README](../README.md#environment-variables).

## 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
python app.py
# API on http://localhost:5050
```

On first boot the backend creates its SQLite database and runs migrations automatically (Alembic,
via `PersistenceMixin`) — nothing to run by hand. Verify it's alive:

```bash
curl http://localhost:5050/health
# {"status": "ok", "timestamp": 1720000000.0}
```

## 3. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
# Dashboard on http://localhost:5173
```

Vite proxies API calls to `http://127.0.0.1:5050`, so the two talk to each other with no extra
config. Open **http://localhost:5173** — the dashboard loads, empty until a device shows up.

> **Shortcut:** `dev.bat` (Windows) or `./dev.sh` (macOS/Linux) launches both servers at once.
>
> **Even faster:** `docker-compose up` runs the full stack (frontend on `:3847`, API on `:5890`,
> local DynamoDB on `:8321`). Good for a demo; the manual path above is better for development.

## 4. Connect a device

DeviceKit merges two kinds of devices into one fleet: **ADB-connected** devices and
**agent-registered** devices. You need either.

### Option A — USB (ADB)

Plug in a device with USB debugging enabled and confirm ADB sees it:

```bash
adb devices -l   # your device should show "device", not "unauthorized"
```

That's it. The backend refreshes from ADB on every `GET /devices`, so the device appears in the
dashboard automatically — and it offers to push the agent APK to devices that don't have it yet.

### Option B — the agent app (USB or WiFi)

The Kotlin agent runs an on-device HTTP server (port 9800) and reports metrics/state up to the
backend. The backend serves the APK at `GET /agent/apk`, or build it from `agent-android/` (see
the `build-agent-apk` skill).

- **Over WiFi:** put the phone and your machine on the same network; the agent auto-discovers the
  backend (UDP 9801) and starts reporting. No cables.
- **Over USB:** the agent reaches the backend through a reverse tunnel — run this once per device:

  ```bash
  adb -s <SERIAL> reverse tcp:5050 tcp:5050
  ```

  Without it the agent sits in "Connecting…" / standalone mode. See
  [Fleet Contract](FLEET_CONTRACT.md) for the exact registration flow and
  [Architecture](ARCHITECTURE.md#connection-flow) for why.

Either way, confirm the device is there:

```bash
curl http://localhost:5050/devices
# {"devices": [ { "device_id": "...", "model": "...", "online": true, ... } ], "count": 1}
```

## 5. Run your first automation

### From the dashboard (no code)

1. Go to **Automations → New** to open the visual editor.
2. Add steps from the palette — `tap`, `swipe`, `type`, `open_app`, `screenshot`, and
   [11 more](../README.md#automation-engine). Every step type renders its own config form.
3. *(optional)* Expand **Generate with AI**, describe what you want in plain English
   ("Open Settings, go to Wi-Fi, screenshot the list"), and accept the generated steps. This
   needs a Prompture key — see [AI Agent](ai-agent.md).
4. Save, then **Run** it against your device. Watch step-by-step progress live; a failed step
   auto-captures a screenshot and a [debug bundle](../README.md#failure-debug-bundles).

### From Python (droidlink)

Prefer scripts or CI? Talk to the device directly with the
[droidlink](droidlink.md) library — no backend required for device control:

```python
import droidlink

d = droidlink.connect("<SERIAL>")     # USB (handles the adb forward for you)
d.app.launch("com.android.settings")
d(text="Wi-Fi").click()
d.screenshot("wifi.png")
```

`pip install droidlink` first. The same library drives tests in CI — see
[CI/CD Setup](ci-setup.md) and the [droidlink guide](droidlink.md).

---

## Where to next

- **Understand the system** → [Architecture](ARCHITECTURE.md)
- **Build an extension** → [First Extension Tutorial](extensions/tutorial.md)
- **Drive devices from Python / CI** → [droidlink](droidlink.md)
- **Use the AI layer** → [AI Agent](ai-agent.md)
- **Build a non-Kotlin agent / debug enrollment** → [Fleet Contract](FLEET_CONTRACT.md)

## Troubleshooting the first run

| Symptom | Fix |
| --- | --- |
| Device shows `unauthorized` in `adb devices` | Accept the RSA debugging prompt on the phone screen. If none appears, revoke USB debugging authorizations in Developer options and replug. |
| Agent stuck on "Connecting…" | The agent can't reach the backend. Over USB, run `adb -s <SERIAL> reverse tcp:5050 tcp:5050`. Over WiFi, set the backend URL to your machine's IP in agent settings. |
| Backend won't start / DB error | Delete `backend/devicekit.db` to recreate from scratch (dev only — this drops all saved automations, groups, and queries). |
| AI routes return an error | Set `PROMPTURE_DEFAULT_MODEL` and the matching provider key in `.env`, then restart the backend. |

The [root README's Troubleshooting section](../README.md#troubleshooting) covers streaming and
Docker-specific issues.
