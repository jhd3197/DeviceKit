import os
from dotenv import load_dotenv

load_dotenv()

# API
API_PORT = int(os.getenv("API_PORT", 7317))
API_HOST = os.getenv("API_HOST", "0.0.0.0")

# AWS
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# DynamoDB
DYNAMODB_TABLE_PREFIX = os.getenv("DYNAMODB_TABLE_PREFIX", "devicekit_")
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT", None)

# Persistence (SQLAlchemy)
# Default: embedded SQLite file next to the backend. Set DEVICEKIT_DATABASE_URL to a
# Postgres URL (e.g. postgresql+psycopg2://user:pass@host/db) to scale out.
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devicekit.db")
DEVICEKIT_DATABASE_URL = os.getenv(
    "DEVICEKIT_DATABASE_URL",
    f"sqlite:///{_DEFAULT_DB_PATH}",
)

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Devices
DEVICE_IDS = [d.strip() for d in os.getenv("DEVICE_IDS", "").split(",") if d.strip()]

# Auth
API_KEY = os.getenv("API_KEY", "")  # Empty = auth disabled (dev mode)
AGENT_TOKENS = [t.strip() for t in os.getenv("AGENT_TOKENS", "").split(",") if t.strip()]

# Agent security & fleet registry (plan 07)
# Heartbeat reaper: a device with no heartbeat for this many seconds is marked offline
# (ServerKit uses 90s; the old inline sweep used an aggressive 15s).
AGENT_HEARTBEAT_TIMEOUT = float(os.getenv("AGENT_HEARTBEAT_TIMEOUT", "90"))
# HMAC replay guard: reject a signed request whose timestamp is outside this window.
AGENT_HMAC_WINDOW = float(os.getenv("AGENT_HMAC_WINDOW", "60"))
# When true, only enrolled devices (with an issued secret) may register/report — the open
# `/agent-device/register` path is rejected. Off by default so dev + existing agents keep
# working; turn on once agents ship the pairing/HMAC path.
AGENT_ENROLLMENT_REQUIRED = os.getenv("AGENT_ENROLLMENT_REQUIRED", "false").lower() in ("true", "1", "yes")
# Default per-command dispatch timeout (seconds) for synchronous agent commands.
AGENT_COMMAND_TIMEOUT = float(os.getenv("AGENT_COMMAND_TIMEOUT", "30"))

# OTA agent updates (plan 25 part 3)
# Ed25519 private key used to sign release manifests. Generated + persisted on first use.
# The agent pins the matching public key. Keep this file out of backups' plaintext.
OTA_SIGNING_KEY_PATH = os.getenv(
    "DEVICEKIT_OTA_KEY_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "ota", "signing_key.pem"))
# How often the scheduled advance job progresses active rollouts (canary→staged→full).
OTA_ROLLOUT_ADVANCE_INTERVAL = int(os.getenv("DEVICEKIT_OTA_ADVANCE_INTERVAL", "60"))
# Crash-loop backoff: a device that fails an install this many times stops being offered it.
OTA_MAX_UPDATE_ATTEMPTS = int(os.getenv("DEVICEKIT_OTA_MAX_UPDATE_ATTEMPTS", "3"))

# Backup / DR of DeviceKit's own state (plan 25 part 6)
# How often the scheduled restore drill runs (default daily). The drill restores the latest
# backup into a throwaway scratch DB and tears it down — it never touches live.
BACKUP_DRILL_INTERVAL = int(os.getenv("DEVICEKIT_BACKUP_DRILL_INTERVAL", "86400"))
# Keep this many most-recent backups on disk (older ones are pruned after a new one lands).
BACKUP_RETENTION = int(os.getenv("DEVICEKIT_BACKUP_RETENTION", "7"))

# AI Agent (Prompture)
PROMPTURE_DEFAULT_MODEL = os.environ.get("PROMPTURE_DEFAULT_MODEL", "claude/claude-sonnet-4-20250514")

# Debug
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() in ("true", "1", "yes")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Table names
TABLE_DEVICES = f"{DYNAMODB_TABLE_PREFIX}devices"
TABLE_ALERTS = f"{DYNAMODB_TABLE_PREFIX}alerts"
TABLE_ACTIVITIES = f"{DYNAMODB_TABLE_PREFIX}activities"
TABLE_QUEUES = f"{DYNAMODB_TABLE_PREFIX}queues"
TABLE_CONFIG = f"{DYNAMODB_TABLE_PREFIX}config"
TABLE_BUILDS = f"{DYNAMODB_TABLE_PREFIX}builds"
