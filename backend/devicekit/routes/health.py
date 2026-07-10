"""Health check route."""
import time

from flask import Blueprint, jsonify


def make_blueprint(client, limiter):
    bp = Blueprint('health', __name__)

    @bp.route('/health')
    def health():
        return jsonify({'status': 'ok', 'timestamp': time.time()})

    return bp
