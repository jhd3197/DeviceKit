"""The request authorization gate (plan 20).

Factored out of ``api_app``'s ``before_request`` so the real app and the test-suite exercise the
*same* decision function. Given a client (the mixin composite) and a Flask ``request``, it returns
``(principal, error)`` where ``error`` is either ``None`` or an ``(body_dict, status)`` pair the
caller turns into a JSON response.

The order of checks: public paths → the agent-token machine axis → principal resolution → the
per-feature write gate.
"""
from devicekit.services.principal import feature_for_path

# Reachable without an authenticated principal: health for liveness, and the auth-discovery
# endpoints so the SPA can learn *whether* login is required before it has a token.
PUBLIC_PATHS = ('/health', '/auth/login', '/auth/logout', '/auth/session')

_WRITE_METHODS = ('POST', 'PUT', 'DELETE', 'PATCH')


def authorize(client, request):
    """Resolve the principal and authorize the request.

    Returns ``(principal, error)``. ``error`` is ``None`` when the request may proceed, else an
    ``({'error': msg}, status_code)`` pair. ``principal`` is always set except on a hard auth
    failure (``None`` with a 401)."""
    if request.path in PUBLIC_PATHS or request.method == 'OPTIONS':
        return client.anonymous_principal(), None

    # Agent-device endpoints authenticate on the machine token, orthogonal to human RBAC.
    if request.path.startswith('/agent-device/'):
        token = request.headers.get('X-Agent-Token', '')
        if not client.validate_agent_token(token):
            return None, ({'error': 'Invalid agent token'}, 401)
        return client.agent_principal(), None

    principal = client.resolve_principal(request)
    if principal is None:
        return None, ({'error': 'Authentication required'}, 401)

    if request.method in _WRITE_METHODS:
        feature = feature_for_path(request.path)
        if feature and not principal.can(feature, 'write'):
            return principal, ({'error': 'Insufficient permissions'}, 403)

    return principal, None
