import os
from dotenv import load_dotenv

load_dotenv()

# API
API_PORT = int(os.getenv("API_PORT", 5050))
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
