"""The `/api/v1` meta surface (plan 21): discovery, the scope catalog, and the spec.

The versioned API itself is the mirror of every route blueprint under ``/api/v1`` (see
``register_all``); this module only adds the endpoints that exist *because* the surface is
public — what version this is, how to authenticate, which scopes a ``dk_`` key can hold,
and the auto-generated OpenAPI document + rendered docs page (no hand-maintained spec).
"""
from flask import Blueprint, current_app, jsonify

from devicekit.services.api_docs_page import DOCS_HTML
from devicekit.services.openapi import generate_openapi
from devicekit.services.scopes import describe_scopes


def make_blueprint(client, limiter):
    bp = Blueprint('api_v1', __name__)

    @bp.route('/api/v1')
    def api_v1_index():
        """Public API discovery: version, auth schemes, and where to find the spec."""
        return jsonify({
            'service': 'devicekit',
            'api_version': 'v1',
            'scopes_url': '/api/v1/scopes',
            'openapi_url': '/api/v1/openapi.json',
            'docs_url': '/api/v1/docs',
            'auth': {
                'schemes': [
                    {'type': 'api_key', 'header': 'X-API-Key', 'key_prefix': 'dk_'},
                    {'type': 'session', 'header': 'X-Session-Token',
                     'alt': 'Authorization: Bearer <token>'},
                ],
            },
        })

    @bp.route('/api/v1/scopes')
    def api_v1_scopes():
        """The assignable scope catalog with descriptions, for integrators."""
        scopes = describe_scopes()
        return jsonify({'scopes': scopes, 'count': len(scopes)})

    @bp.route('/api/v1/openapi.json')
    def api_v1_openapi():
        """OpenAPI 3.0 spec, generated live from the url_map — always in sync."""
        return jsonify(generate_openapi(current_app))

    @bp.route('/api/v1/docs')
    def api_v1_docs():
        """Rendered API reference (self-contained page over the generated spec)."""
        return DOCS_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

    return bp
