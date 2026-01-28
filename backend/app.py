"""DeviceKit Backend - Flask Entrypoint"""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import API_PORT, API_HOST, LOG_LEVEL
from devicekit import Client
import logging

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

if __name__ == '__main__':
    client = Client()
    client.api_app(host=API_HOST, port=API_PORT, debug=True)
