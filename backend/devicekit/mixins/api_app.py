import logging

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.routes import register_all

logger = logging.getLogger(__name__)


class ApiAppMixin:
    """Builds the Flask app: cross-cutting middleware + blueprint registration.

    Every route group is a blueprint under ``devicekit/routes/`` (plan 02). This mixin
    owns only the app factory and the app-wide concerns (CORS, rate limiting, auth,
    security headers, audit logging). The pipeline blueprint's in-memory build store and
    the config blueprint's settings dict live here as shared client state.
    """

    # In-memory stores owned by the pipeline / config blueprints.
    _builds = []
    _config = {}

    def build_app(self):
        """Construct and configure the Flask app without starting the server.

        Kept separate from ``api_app()`` so the route table can be introspected and
        tested without booting the dev server.
        """
        app = Flask(__name__)
        from config import CORS_ORIGINS
        CORS(app, origins=CORS_ORIGINS)
        client = self

        limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"],
                          storage_uri="memory://")

        @app.before_request
        def check_auth():
            # Skip auth for health, CORS preflight, SSE
            if request.path in ('/health',) or request.method == 'OPTIONS':
                return None
            # Agent device endpoints use agent token
            if request.path.startswith('/agent-device/'):
                token = request.headers.get('X-Agent-Token', '')
                if not client.validate_agent_token(token):
                    return jsonify({'error': 'Invalid agent token'}), 401
                return None
            # SSE endpoint: allow query param fallback (EventSource can't send headers)
            if request.path == '/events/stream':
                key = request.headers.get('X-API-Key') or request.args.get('api_key', '')
                if not client.validate_api_key(key):
                    return jsonify({'error': 'Invalid API key'}), 401
                return None
            # Stream endpoint: allow query param fallback (MJPEG streams can't send headers)
            if '/stream' in request.path and request.path.startswith('/devices/'):
                key = request.headers.get('X-API-Key') or request.args.get('api_key', '')
                if not client.validate_api_key(key):
                    return jsonify({'error': 'Invalid API key'}), 401
                return None
            # All other endpoints use API key
            key = request.headers.get('X-API-Key', '')
            if not client.validate_api_key(key):
                return jsonify({'error': 'Invalid API key'}), 401
            return None

        @app.after_request
        def add_security_headers(response):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            return response

        @app.after_request
        def audit_log(response):
            if request.method in ('POST', 'PUT', 'DELETE') and response.status_code < 500:
                client.log_activity(
                    action=f"{request.method} {request.path}",
                    details={'status': response.status_code},
                    source_ip=request.remote_addr,
                    authenticated=bool(request.headers.get('X-API-Key') or request.headers.get('X-Agent-Token')),
                )
            return response

        # Mount every route group. URLs are identical to the pre-refactor closures.
        register_all(app, client, limiter)

        # Boot the extension platform: hot-load every active extension's blueprint onto the
        # app while it is still safe to register (before the first request). Runtime installs
        # register through the same path with a flag-flip (see ExtensionsMixin).
        self._flask_app = app
        try:
            self.load_all_extensions(app)
        except Exception as e:
            logger.warning(f"Extension boot load skipped: {e}")

        return app

    def api_app(self, host='0.0.0.0', port=5050, debug=True):
        try:
            self.start_uiautomator2_server()
        except Exception as e:
            logger.warning(f"UIAutomator2 init skipped: {e}")

        app = self.build_app()
        app.run(host=host, port=port, debug=debug)
        return app
