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

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Devices
DEVICE_IDS = [d.strip() for d in os.getenv("DEVICE_IDS", "").split(",") if d.strip()]

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Table names
TABLE_DEVICES = f"{DYNAMODB_TABLE_PREFIX}devices"
TABLE_ALERTS = f"{DYNAMODB_TABLE_PREFIX}alerts"
TABLE_ACTIVITIES = f"{DYNAMODB_TABLE_PREFIX}activities"
TABLE_QUEUES = f"{DYNAMODB_TABLE_PREFIX}queues"
TABLE_CONFIG = f"{DYNAMODB_TABLE_PREFIX}config"
TABLE_BUILDS = f"{DYNAMODB_TABLE_PREFIX}builds"
