# DeviceKit

Unified Android device management platform. Combines CrawlerAndroid's Python/Flask backend with a React frontend for fleet monitoring, remote ADB, pipeline automation, and device diagnostics.

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
│       └── mixins/             ADB, UIAutomator2, CDP, DynamoDB, S3, Queue, Alerts, Activity, API
├── frontend/         React 18 + Vite + Tailwind CSS
│   └── src/
│       ├── App.jsx   Router + sidebar layout
│       ├── api.js    API client
│       └── views/    Dashboard, NodeDetail, Pipeline, RemoteADB
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
# Frontend: http://localhost:3000
# API: http://localhost:5050
# DynamoDB Local: http://localhost:8000
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
| `DYNAMODB_ENDPOINT` | - | Local DynamoDB URL (e.g. `http://localhost:8000`) |
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

## Tech Stack

**Backend:** Python 3.11, Flask, boto3, uiautomator2, pychrome, BeautifulSoup

**Frontend:** React 18, Vite, Tailwind CSS 3, Lucide React, React Router v6

**Infrastructure:** Docker, nginx, DynamoDB Local
