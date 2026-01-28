# DeviceKit

Unified Android device management platform. Combines CrawlerAndroid's Python/Flask backend with a React frontend for fleet monitoring, remote ADB, pipeline automation, device diagnostics, and workflow automations.

## Architecture

```
DeviceKit/
├── backend/          Python/Flask API (port 5050)
│   ├── app.py        Entrypoint
│   ├── config.py     Environment config
│   └── devicekit/    Core package
│       ├── client.py           Mixin composition class
│       ├── device_manager.py   Thread-safe device pool
│       ├── tools.py            Utilities
│       └── mixins/             ADB, UIAutomator2, CDP, DynamoDB, S3, Queue, Alerts, Activity, Automation, API
├── frontend/         React 18 + Vite + Tailwind CSS
│   └── src/
│       ├── App.jsx   Router + sidebar layout
│       ├── api.js    API client
│       └── views/    Dashboard, NodeDetail, Pipeline, RemoteADB, Automations
└── template/         HTML design references
```

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
# API runs on http://localhost:5050
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Dev server on http://localhost:5173
```

### Docker

```bash
cp .env.example .env
# Edit .env with your AWS credentials
docker-compose up
# Frontend: http://localhost:3847
# API: http://localhost:5890
# DynamoDB Local: http://localhost:8321
```

### Docker (Dev)

```bash
docker-compose -f docker-compose.dev.yml up
# Frontend: http://localhost:5891
# API: http://localhost:5890
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `5050` | Flask API port |
| `API_HOST` | `0.0.0.0` | Flask bind address |
| `AWS_ACCESS_KEY_ID` | - | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | - | AWS credentials |
| `AWS_REGION` | `us-east-1` | AWS region |
| `DYNAMODB_TABLE_PREFIX` | `devicekit_` | Table name prefix |
| `DYNAMODB_ENDPOINT` | - | Local DynamoDB URL (e.g. `http://localhost:8321`) |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `DEVICE_IDS` | - | Comma-separated device serials |
| `LOG_LEVEL` | `INFO` | Logging level |

## API Endpoints

### Core
- `GET /health` - Health check
- `GET /devices` - List connected devices
- `GET /devices/:id` - Device info

### Dashboard
- `GET /dashboard/stats` - Fleet metrics

### Device Control
- `POST /devices/:id/adb` - Execute ADB command
- `POST /devices/:id/reboot` - Reboot device
- `GET /devices/:id/screenshot` - Screenshot (PNG)
- `GET /devices/:id/battery` - Battery info
- `GET /devices/:id/diagnostics` - CPU, RAM, temp, uptime
- `GET /devices/:id/properties` - OS, kernel, hardware
- `GET /devices/:id/files` - File listing

### Pipeline
- `GET /pipeline/builds` - List builds
- `GET /pipeline/builds/:id` - Build detail
- `POST /pipeline/builds` - Start build
- `GET /pipeline/builds/:id/failures` - Failure analysis

### Queue
- `GET /queue/status` - All queue counts
- `POST /queue/:name/send` - Enqueue message
- `POST /queue/:name/receive` - Dequeue message

### Alerts & Activities
- `GET /alerts` - List alerts
- `POST /alerts` - Create alert
- `PUT /alerts/:id/dismiss` - Dismiss alert
- `GET /activities` - List activities

### Automations
- `GET /automations/step-types` - Available step types
- `GET /automations` - List automations
- `POST /automations` - Create automation
- `GET /automations/:id` - Automation detail
- `PUT /automations/:id` - Update automation
- `DELETE /automations/:id` - Delete automation
- `POST /automations/:id/run` - Run automation on device
- `GET /automations/runs` - List runs
- `GET /automations/runs/:runId` - Run detail
- `POST /automations/runs/:runId/cancel` - Cancel run

### Config
- `GET /config` - Get configuration
- `PUT /config` - Update configuration

## Frontend Views

| View | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Fleet overview with metric cards and node registry table |
| Node Detail | `/node/:id` | Phone mockup, live diagnostics, ADB shell, properties |
| Pipeline | `/pipeline` | Build list, test execution stream, failure analysis |
| Remote ADB | `/remote-adb` | Terminal, file explorer, command presets |
| Automations | `/automations` | Create, edit, and run multi-step device automations |
| Automation Editor | `/automations/new` | Visual step builder with drag-and-drop workflow design |
| Automation Run Detail | `/automations/runs/:runId` | Live run progress, step results, and logs |

## Tech Stack

**Backend:** Python 3.11, Flask, boto3, uiautomator2, pychrome, BeautifulSoup

**Frontend:** React 18, Vite, Tailwind CSS 3, Lucide React, React Router v6

**Infrastructure:** Docker, nginx, DynamoDB Local
