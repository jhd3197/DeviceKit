"""The `/api/v1` meta surface (plan 21): discovery index + the scope catalog.

The versioned API itself is the mirror of every route blueprint under ``/api/v1`` (see
``register_all``); this module only adds the endpoints that exist *because* the surface is
public — what version this is, how to authenticate, and which scopes a ``dk_`` key can hold.
Phase 2 adds ``/api/v1/openapi.json`` + the rendered docs page here.
"""
from flask import Blueprint, jsonify

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

    return bp
