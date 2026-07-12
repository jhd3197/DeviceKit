import logging

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.routes import register_all
from devicekit.services.gate import authorize

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
            # Single shared decision function (also exercised directly by the test-suite).
            # Resolves the principal, attaches it to ``g``, and returns an error response when
            # authentication is missing or the write gate blocks the request.
            principal, error = authorize(client, request)
            g.principal = principal
            if error:
                body, status = error
                return jsonify(body), status
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
            # Durable, user-attributed audit (plan 20 part 3) + the in-memory activity feed.
            # Reads the principal the gate attached to ``g``.
            client.audit_request(request, response, getattr(g, 'principal', None))
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

        # Start the job consumer + scheduler daemons now that the app (and every mixin's
        # handlers) are wired. Reconciles any work interrupted by a previous process first.
        try:
            self.start_job_workers()
        except Exception as e:
            logger.warning(f"Job workers not started: {e}")

        return app

    def api_app(self, host='0.0.0.0', port=7317, debug=True):
        try:
            self.start_uiautomator2_server()
        except Exception as e:
            logger.warning(f"UIAutomator2 init skipped: {e}")

        app = self.build_app()
        app.run(host=host, port=port, debug=debug)
        return app
