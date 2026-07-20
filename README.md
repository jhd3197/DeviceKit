<div align="center">

<img width="130" alt="DeviceKit" src="docs/assets/logo.svg" />

# DeviceKit

**A unified Android device fleet & test-automation platform.**

Control a fleet of Android devices from one dashboard — run automations, stream
screens in real time, catch visual regressions, and debug failures with
AI-powered analysis.

English | [Español](docs/README.es.md) | [中文版](docs/README.zh-CN.md) | [Português](docs/README.pt.md)

<br>

![Android](https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Kotlin](https://img.shields.io/badge/Kotlin-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
[![Discord](https://img.shields.io/discord/1470639209059455008?style=for-the-badge&logo=discord&logoColor=white&label=Discord&color=5865F2)](https://discord.gg/ZKk6tkCQfG)

[![GitHub Stars](https://img.shields.io/github/stars/jhd3197/DeviceKit?style=flat-square&color=f5c542)](https://github.com/jhd3197/DeviceKit/stargazers)
[![Downloads](https://img.shields.io/github/downloads/jhd3197/DeviceKit/total?style=flat-square)](https://github.com/jhd3197/DeviceKit/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/react-18-61DAFB.svg?style=flat-square&logo=react&logoColor=black)](https://reactjs.org)
[![Flask](https://img.shields.io/badge/flask-3.0-000000.svg?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![PyPI](https://img.shields.io/badge/pip-droidlink-3775A9.svg?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/droidlink/)

<br>

[Quick Start](#-quick-start) · [Screenshots](#-screenshots) · [Features](#-features) · [Architecture](#-architecture) · [Roadmap](#-roadmap) · [Docs](#-documentation) · [Contributing](#-contributing) · [Discord](#-community)

</div>

---

<p align="center">
  <img alt="DeviceKit Fleet Overview" width="100%" src="docs/screenshots/dashboard.png" />
</p>

---

## Why DeviceKit?

Managing Android devices for testing usually means juggling ADB commands across
terminals, manually tracking which device is running what, and digging through
logs when something breaks. DeviceKit takes a different approach: a single
platform that discovers your devices, lets you control them from a web
dashboard, and automates the tedious parts.

The whole thing is **four components working together** — a Python/Flask backend
that manages device state and orchestrates actions, a React frontend for the
dashboard and visual editors, a Kotlin agent app that runs on each device to
report metrics and accept commands, and a Python library
([`pip install droidlink`](https://pypi.org/project/droidlink/)) for scripts and
CI pipelines. You get **AI-powered automation** out of the box: describe what you
want in plain English, and DeviceKit generates executable steps; when UI elements
move between app versions, self-healing retries find them again; when tests fail,
debug bundles package screenshots, logs, UI hierarchy, and device state into one
download — with optional AI root-cause analysis.

---

## 🚀 Quick Start

> ⏱️ Plug in a device and it shows up automatically.

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/jhd3197/DeviceKit.git
cd DeviceKit
cp .env.example .env
docker-compose up
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3847 |
| API | http://localhost:5890 |
| DynamoDB (local) | http://localhost:8321 |

### Option 2: Manual Setup

```bash
# Backend
cd backend
pip install -r requirements.txt
python app.py                # API on http://localhost:5050

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev                  # dev server on http://localhost:5173
```

### Connect a Device

```bash
# USB : just plug in the device (ADB / USB debugging enabled)
# WiFi: install the agent APK — same network, auto-discovers the backend
```

**Need the agent app?** The backend serves it at `GET /agent/apk`, or build from
`agent-android/`.

### Drive it from Python

```python
# pip install droidlink — the same fleet, from a script or CI
def test_login_flow(device):
    device.app.start("com.example.app")
    device.input.tap(540, 1200)
    device.input.type_text("user@test.com")
    assert device.screen.capture() is not None
```

---

<!-- DK:SHOTS:START -->
## 📸 Screenshots

|                          Fleet Overview                           |                           Node Control                           |
| :---------------------------------------------------------------: | :--------------------------------------------------------------: |
|      ![Fleet Overview](docs/screenshots/dashboard.png)      |     ![Node Control](docs/screenshots/node-detail.png)      |
|   _Live fleet metrics, KPI cards, health distribution, active runs, recent failures, and the FQL query bar_   |   _Per-device live stream, live diagnostics gauges, ADB shell, metrics history, and macro quick-actions_   |

|                          Automation Run                           |                         Automation Editor                         |
| :---------------------------------------------------------------: | :---------------------------------------------------------------: |
|    ![Automation Run](docs/screenshots/automation-run.png)    |  ![Automation Editor](docs/screenshots/automation-editor.png)  |
|   _Live per-step results, self-healing (original → healed diff), visual-regression asserts, and an auto-generated debug bundle with AI analysis on failure_   |   _Step builder with reorder + per-step AI refine, "Generate with AI", tags, and visual baselines_   |

|                          Workflow Builder                          |                           Automations                           |
| :----------------------------------------------------------------: | :-------------------------------------------------------------: |
|      ![Workflow Builder](docs/screenshots/workflow.png)      |      ![Automations](docs/screenshots/automations.png)      |
|   _Node-based visual automation canvas — chain triggers, taps, waits, asserts, and branches_   |   _Every automation with steps, tags, run/schedule/share/clone controls, and a recent-runs feed_   |

|                          Device Compare                           |                          Metrics Monitor                           |
| :---------------------------------------------------------------: | :----------------------------------------------------------------: |
|        ![Device Compare](docs/screenshots/compare.png)        |        ![Metrics Monitor](docs/screenshots/monitor.png)        |
|   _Up to 4 devices side by side with a synchronized historical-trend overlay and per-device gauges_   |   _Cross-device metric charts over selectable periods, plus threshold-based alert rules on the notification bus_   |

<details>
<summary><strong>View all screenshots</strong></summary>

<br>

|                           Device Groups                           |                           Pipeline / CI                           |
| :---------------------------------------------------------------: | :---------------------------------------------------------------: |
|        ![Device Groups](docs/screenshots/groups.png)        |        ![Pipeline / CI](docs/screenshots/pipeline.png)        |
|   _Tagged, color-coded groups with bulk actions — reboot, lock, install, run automations_   |   _Build list, per-test results, and failure screenshots from the droidlink pytest plugin_   |

|                             Profiles                             |                            Remote ADB                            |
| :--------------------------------------------------------------: | :--------------------------------------------------------------: |
|          ![Profiles](docs/screenshots/profiles.png)          |        ![Remote ADB](docs/screenshots/remote-adb.png)        |
|   _Per-device AI personalities and multi-provider model config (Claude, GPT, Groq, Ollama, Google)_   |   _In-browser ADB shell with command history and presets, plus a file explorer_   |

|                            Enrollment                            |                         Command History                         |
| :--------------------------------------------------------------: | :-------------------------------------------------------------: |
|         ![Enrollment](docs/screenshots/enrollment.png)         |   ![Command History](docs/screenshots/command-history.png)   |
|   _Agent pairing and approval queue with LAN auto-discovery for new devices_   |   _A fleet-wide timeline of every command issued, with status and who ran it_   |

|                               Jobs                               |                          Notifications                          |
| :--------------------------------------------------------------: | :-------------------------------------------------------------: |
|              ![Jobs](docs/screenshots/jobs.png)              |     ![Notifications](docs/screenshots/notifications.png)     |
|   _Queued, running, and completed background jobs — automations, bulk installs, baseline captures_   |   _Onboarding + alert feed with delivery channels (webhook, Slack, email)_   |

|                            Extensions                            |                             Settings                             |
| :--------------------------------------------------------------: | :--------------------------------------------------------------: |
|         ![Extensions](docs/screenshots/extensions.png)         |          ![Settings](docs/screenshots/settings.png)          |
|   _Installed extensions plus a remote registry to browse and one-click install more_   |   _Instance identity, API access, 2FA, AI/streaming/debug-bundle config, and appearance/white-label branding_   |

</details>
<!-- DK:SHOTS:END -->

---

## 🎯 Features

### 🛰️ Fleet Management

| | |
|---|---|
| **Real-time metrics**<br>CPU, RAM, battery, temperature, and storage per device, streamed live. | **Fleet health**<br>Aggregated healthy / warning / critical distribution across the whole fleet. |
| **Device groups**<br>Tags, color coding, and bulk actions on any selection. | **Device compare**<br>Up to 4 devices side by side with synchronized real-time charts. |
| **Auto-onboarding**<br>New devices announce themselves the moment they connect. | **Command history**<br>A fleet-wide audit timeline of every action issued. |

### 🔎 Fleet Query Language

| | |
|---|---|
| **SQL-like filtering**<br>`android_version < 13 AND battery > 20 AND status = 'idle'` | **Autocomplete + presets**<br>Field completion in the query bar, plus built-ins (low battery, offline, outdated OS). |
| **Saved queries**<br>Store the filters you reach for. | **Query → bulk action**<br>Pipe results straight into reboot, lock, install APK, or run-automation. |
| **CSV export**<br>Take any query result out with you. | |

### 🤖 Automation Engine

| | |
|---|---|
| **14 step types**<br>Tap, swipe, type, press key, open/close app, push/pull files, wait, assert, screenshot, and more. | **Drag-and-drop editor**<br>Visual step builder with previews and live device context. |
| **Workflow builder**<br>Node-based canvas for branching, multi-step automations. | **Record automations**<br>Tap and swipe on the device; get generated steps back. |
| **Schedule & share**<br>Run on intervals with pause/resume; clone, export, and import as JSON. | |

### ✨ AI-Powered Automation

| | |
|---|---|
| **Generate**<br>Turn a plain-English description into executable automation steps. | **Refine**<br>Modify individual steps with conversational instructions. |
| **Explain**<br>Get a plain-English summary of what any automation does. | **Self-healing**<br>When UI elements move between app versions, AI re-locates targets and retries automatically. |

### 🖼️ Visual Regression Testing

| | |
|---|---|
| **Screenshot assertions**<br>A `screenshot_assert` step compares against stored baselines. | **SSIM diff engine**<br>Pixel diff with configurable thresholds. |
| **AI diff analysis**<br>Distinguishes meaningful UI changes from rendering noise. | **Region masking**<br>Exclude dynamic content (clocks, ads, timestamps). |
| **Per-model baselines**<br>Baselines tracked per device model and version, with pass / fail / needs-review reports. | |

### 📺 Live Device Streaming

| | |
|---|---|
| **MJPEG streaming**<br>Real-time video, not screenshot polling, with adaptive quality (5 / 15 / 30 fps). | **Multi-viewer**<br>Viewer-count badges and shared sessions. |
| **Touch overlay**<br>Ripple animations show every interaction. | **Session recording**<br>Frame-by-frame playback with event markers. |
| **Latency indicator**<br>Green (<100 ms), yellow (<300 ms), red (>300 ms), with auto-fallback to screenshot polling. | |

### 🧰 Failure Debug Bundles

| | |
|---|---|
| **Auto-generated**<br>Created on any automation-step or test failure. | **Everything in one package**<br>Screenshot, logcat (last 100 lines), device state, UI hierarchy XML, recent actions, and device properties. |
| **AI analysis**<br>Sends the bundle for a root-cause hypothesis and suggested fixes. | **Shareable**<br>Time-limited links to share bundles with teammates; download as ZIP, 30-day retention. |

### 🔬 CI/CD Integration

| | |
|---|---|
| **droidlink pytest plugin**<br>`device` and `device_pool` fixtures, `pip install droidlink`. | **Auto-screenshot on failure**<br>Every failing test captures device state. |
| **Build tracking**<br>Per-test results tied to a build lifecycle. | **Parallel-safe**<br>Device locking for parallel test runners, with a GitHub Actions template included. |

### 🖥️ Remote Control & AI Agents

| | |
|---|---|
| **Remote ADB & files**<br>In-browser ADB shell with history and presets, plus a searchable file explorer. | **Prompture AI agents**<br>Each device becomes a conversational agent: multi-provider (Claude, GPT, Groq, Ollama, Google), per-device model + memory, direct tool use, and token/cost tracking. |
| **Extensions**<br>A bundled catalog and remote registry, with an installed-extensions manager. | |

---

## 🏗️ Architecture

```
                        ┌────────────────────┐
                        │   React Frontend   │  Dashboard, visual editors,
                        │   (Vite/Tailwind)  │  live streams — SSE + REST
                        └─────────┬──────────┘
                                  │  REST API + SSE
                        ┌─────────┴──────────┐
                        │   Flask Backend    │  Merges ADB + agent devices
              ┌─────────┤   (31 mixins)      ├─────────┐  into one fleet
              │         └─────────┬──────────┘         │
      DynamoDB│ / S3              │ ADB / HTTP          │ REST
              ▼                   ▼                     ▼
     ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐
     │  Persistence   │  │  Android Agent  │  │ pytest+droidlink │
     │  + File store  │  │  (Kotlin app)   │  │  scripts + CI    │
     └────────────────┘  │  HTTP :9800     │  └──────────────────┘
                         │  UDP  :9801     │
                         └─────────────────┘
```

1. **Android agent** runs on each device — serves an HTTP API on port 9800 and reports metrics to the backend
2. **Flask backend** merges ADB-connected and agent-registered devices into a unified fleet
3. **React frontend** subscribes to SSE for real-time updates, REST for everything else
4. **droidlink library** connects directly to devices for scripts and CI — USB via ADB port forwarding, WiFi via auto-discovery
5. **pytest plugin** allocates devices, runs tests, and reports results back to the dashboard

**[Full architecture →](docs/ARCHITECTURE.md)** · **[Fleet contract →](docs/FLEET_CONTRACT.md)**

---

## 🗺️ Roadmap

- [x] Fleet management — real-time metrics, health aggregation, device groups, compare
- [x] Fleet Query Language — SQL-like filtering, presets, query → bulk action, CSV export
- [x] Automation engine — 14 step types, drag-and-drop editor, record, schedule, share
- [x] Workflow builder — node-based visual automation canvas
- [x] AI automation — generate / refine / explain from natural language
- [x] Self-healing — AI re-locates moved UI targets and retries
- [x] Visual regression — SSIM diff, AI analysis, region masking, per-model baselines
- [x] Live streaming — MJPEG, adaptive quality, touch overlay, session recording
- [x] Debug bundles — auto-capture, AI root-cause, shareable links
- [x] CI/CD — droidlink pytest plugin, parallel device locking, GitHub Actions template
- [x] Prompture AI agents — per-device conversational agents with tool use
- [x] Remote ADB & file explorer
- [x] Agent fleet — enrollment, approval queue, LAN discovery, command queue, staged updates
- [x] Extensions — bundled catalog + remote registry
- [x] Appearance — light / dark / system themes, accent colors, white-label branding
- [ ] Public API + MCP server — scoped `dk_` keys, auto-OpenAPI, `devicekit` CLI

Full history and upcoming phases: **[ROADMAP.md](ROADMAP.md)**

---

## 📖 Documentation

The full documentation suite lives in **[`docs/`](docs/README.md)** — start there
for the map. The highlights:

| Guide | Description |
| --- | --- |
| [Documentation Index](docs/README.md) | The map — every doc, grouped by what it answers |
| [Getting Started](docs/getting-started.md) | Install → run backend → connect a device → first automation |
| [Architecture](docs/ARCHITECTURE.md) | The four components and how they talk (read this first) |
| [Fleet Contract](docs/FLEET_CONTRACT.md) | Agent ↔ backend protocol: register/heartbeat/state/commands, HMAC, capabilities |
| [Extension Guide](docs/extensions/guide.md) | Build an extension — contribution points, SDK, manifest, tutorial |
| [AI Agent](docs/ai-agent.md) | Prompture-backed device agents: tools, confirmation gate, session modes |
| [droidlink](docs/droidlink.md) | Drive a DeviceKit-managed fleet from Python (`pip install droidlink`) |
| [CI/CD Setup](docs/ci-setup.md) | GitHub Actions integration, device fixtures, parallel testing |
| [MCP Server](docs/mcp-server.md) | Model Context Protocol surface for AI agents |
| [Roadmap](ROADMAP.md) | Full development history and upcoming phases |

---

## 🧱 Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, Flask, 31 composable mixins, SSE |
| Frontend | React 18, Vite, Tailwind CSS |
| Agent | Kotlin (Android), background service, HTTP server, UDP discovery, accessibility service |
| Library | `droidlink` (PyPI) — CLI + pytest plugin |
| Device control | ADB, UIAutomator2, Chrome DevTools Protocol |
| Persistence | DynamoDB (local or AWS), S3 file storage |
| Streaming | MJPEG proxy with adaptive quality |
| AI | Prompture (multi-provider: Claude, GPT, Groq, Ollama, Google) |

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `5050` | Flask API port |
| `API_HOST` | `0.0.0.0` | Flask bind address |
| `API_KEY` | – | API key for endpoint authentication (disabled if unset) |
| `AGENT_TOKENS` | – | Comma-separated tokens for agent authentication |
| `AWS_ACCESS_KEY_ID` | – | AWS credentials for DynamoDB/S3 |
| `AWS_SECRET_ACCESS_KEY` | – | AWS credentials |
| `AWS_REGION` | `us-east-1` | AWS region |
| `DYNAMODB_TABLE_PREFIX` | `devicekit_` | Table name prefix |
| `DYNAMODB_ENDPOINT` | – | Local DynamoDB URL (e.g. `http://localhost:8321`) |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `DEVICE_IDS` | – | Comma-separated device serials |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DEBUG_MODE` | `false` | Enable Flask debug mode |
| `PROMPTURE_DEFAULT_MODEL` | – | Default AI model for device agents |

---

## ✅ Compatibility

| Component | Requirements |
| --- | --- |
| **Backend** | Python 3.11+ |
| **Frontend** | Node 18+, any modern browser |
| **Android Devices** | Android 7+ (API 24+), USB debugging enabled |
| **Agent App** | Android 8+ (API 26+) for full feature set |
| **Docker** | Docker 20+, docker-compose v2 |
| **OS** | Windows, macOS, Linux |

---

## 🛠️ Troubleshooting

**Device not appearing?** — Verify USB debugging is on, run `adb devices` to
confirm ADB sees it, and check that `adb` is in your PATH.

**Agent stuck on "Connecting…"?** — The agent can't reach the backend. For USB,
run `adb reverse tcp:5050 tcp:5050`; for WiFi, set the backend URL in agent
settings to your machine's IP.

**Stream not loading?** — The agent app must be running; make sure port 9800 is
reachable (`adb forward tcp:9800 tcp:9800` for USB) and try a lower-quality
preset.

**Docker issues?** — Run `docker-compose logs`, ensure ports 3847 / 5890 / 8321
are free, and check `.env` has valid AWS credentials (or use DynamoDB Local).

---

## 🤝 Contributing

Contributions are welcome!

```
fork → feature branch → commit → push → pull request
```

1. **Report bugs** — [GitHub Issues](https://github.com/jhd3197/DeviceKit/issues)
2. **Request features** — [GitHub Discussions](https://github.com/jhd3197/DeviceKit/discussions)
3. **Submit PRs** — Bug fixes, new step types, frontend improvements
4. **Improve docs** — All `.md` files in the repo

---

## 💛 Support DeviceKit

DeviceKit is free and open source. If it saves you time, you can help keep it going:

- ⭐ [Star the repo](https://github.com/jhd3197/DeviceKit) — it costs nothing and helps a lot
- 💖 [GitHub Sponsors](https://github.com/sponsors/jhd3197)
- ☕ [Buy Me a Coffee](https://buymeacoffee.com/jhd3197)

### 💎 Crypto

| | Asset | Network | Address |
|:---:|---|---|---|
| <img src="docs/images/funding/usdt-trc20.png" width="110" alt="QR code for the USDT TRC-20 donation address" /> | **USDT** | **TRC-20** · Tron | `TTiCtqLauF1iSW2YGB3b78KmRxRqoLCgeL` |
| <img src="docs/images/funding/usdt-erc20.png" width="110" alt="QR code for the USDT and ETH ERC-20 donation address" /> | **USDT / ETH** | **ERC-20** · Ethereum | `0xD13D5355Fa214e8317fea2ff192a065BaeC13527` |
| <img src="docs/images/funding/btc.png" width="110" alt="QR code for the Bitcoin donation address" /> | **BTC** | **Bitcoin** | `bc1qatx67n3qxdvuv3arc9j8aytk34f22g02k9c7vr` |
| <img src="docs/images/funding/sol.png" width="110" alt="QR code for the Solana donation address" /> | **SOL** | **Solana** | `AWXzqtBEgUfteHPQtDegsZ6D5y57M3GGdKPD8rR7h6xu` |

TRC-20 has the lowest fees — usually under a dollar — so it's the friendliest
option for a small donation. ERC-20 gas can cost more than the donation itself.

<sub>QR codes are generated locally by [`scripts/generate-funding-qr.mjs`](scripts/generate-funding-qr.mjs), which checksum-validates every address before encoding.</sub>

---

## 🔭 Related Projects

**[ServerKit](https://github.com/jhd3197/ServerKit)** — A lightweight, modern
server control panel for web apps, databases, Docker, and security — self-hosted
infrastructure without the Kubernetes complexity.

**[Faro](https://github.com/jhd3197/faro)** — A modern desktop client for SFTP, FTP, SSH, and S3-compatible storage, from the same author. Save a server once, then browse its files in a dual-pane view and open a terminal against the same SSH session — plus drag-and-drop transfers, one-way directory sync, and edit-in-place. It even has an **Agent Bridge** that lets Claude Code (or any MCP agent) run commands on a box through your authenticated session, with per-command approval and no shared credentials.

> DeviceKit manages your Android fleet from the browser; Faro is the desktop companion for hands-on file transfer, shells, and ad-hoc work across all your boxes. [Grab a build →](https://github.com/jhd3197/faro/releases/latest)

**[LocalKit](https://github.com/jhd3197/LocalKit)** — Spin up local WordPress sites in one click. Each site runs as its own isolated Docker Compose project, and you can push code or push/pull databases straight to your ServerKit server through the `serverkit-localkit` extension.

---

## 💬 Community

[![Discord](https://img.shields.io/badge/Discord-Join_Us-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/ZKk6tkCQfG)

Join the Discord to ask questions, share feedback, or get help with your setup.

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for
full details.

**Android** is a trademark of Google LLC. This project is **not affiliated with,
endorsed by, or sponsored by Google LLC.**

---

<div align="center">

**DeviceKit** — One dashboard for your whole Android fleet.

[Report Bug](https://github.com/jhd3197/DeviceKit/issues) · [Request Feature](https://github.com/jhd3197/DeviceKit/discussions)

Made with ❤️ by [Juan Denis](https://juandenis.com)

</div>
