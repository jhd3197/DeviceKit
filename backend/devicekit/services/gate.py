"""The request authorization gate (plan 20).

Factored out of ``api_app``'s ``before_request`` so the real app and the test-suite exercise the
*same* decision function. Given a client (the mixin composite) and a Flask ``request``, it returns
``(principal, error)`` where ``error`` is either ``None`` or an ``(body_dict, status)`` pair the
caller turns into a JSON response.

The order of checks: public paths → the agent-token machine axis → principal resolution → the
per-feature write gate (users) or per-scope gate (``dk_`` keys, plan 21).

Paths are version-stripped first, so the ``/api/v1`` mirror (plan 21) authorizes exactly like
the bare mount — one decision function for both surfaces.
"""
from devicekit.services.principal import feature_for_path
from devicekit.services.scopes import scope_allows, scope_for_request, strip_version

# Reachable without an authenticated principal: health for liveness, and the auth-discovery
# endpoints so the SPA can learn *whether* login is required before it has a token.
PUBLIC_PATHS = ('/health', '/auth/login', '/auth/logout', '/auth/session')

_WRITE_METHODS = ('POST', 'PUT', 'DELETE', 'PATCH')


def _is_public_invitation(path):
    """The invitation preview/accept flow runs before the user has an account, so it is public.
    Admin invitation management (list/create/revoke) is NOT — it lacks these suffixes."""
    return path.startswith('/invitations/') and (
        path.endswith('/preview') or path.endswith('/accept'))


def _is_public_webhook(path):
    """Inbound automation webhooks (plan 22 part 4): the unguessable token in the URL
    *is* the auth — the route 404s on an unknown token. No principal, no scopes."""
    return path.startswith('/hooks/')


def authorize(client, request):
    """Resolve the principal and authorize the request.

    Returns ``(principal, error)``. ``error`` is ``None`` when the request may proceed, else an
    ``({'error': msg}, status_code)`` pair. ``principal`` is always set except on a hard auth
    failure (``None`` with a 401)."""
    path = strip_version(request.path)
    if path in PUBLIC_PATHS or request.method == 'OPTIONS' \
            or _is_public_invitation(path) or _is_public_webhook(path):
        return client.anonymous_principal(), None

    # Agent-device endpoints authenticate on the machine token, orthogonal to human RBAC.
    if path.startswith('/agent-device/'):
        token = request.headers.get('X-Agent-Token', '')
        if not client.validate_agent_token(token):
            return None, ({'error': 'Invalid agent token'}, 401)
        return client.agent_principal(), None

    principal = client.resolve_principal(request)
    if principal is None:
        return None, ({'error': 'Authentication required'}, 401)

    # Attach the active workspace (plan 20 part 4). Lenient: an unknown/forbidden X-Workspace-Id
    # degrades to no scoping, so this can never turn a valid request into an error.
    resolver = getattr(client, 'resolve_workspace_context', None)
    if resolver is not None:
        principal.workspace_id = resolver(request, principal)

    if principal.scopes is not None and not principal.full_access:
        # Scoped ``dk_`` keys (plan 21): reads need ``<feature>:read``, writes the catalog
        # verb for the path (``devices:command``, ``automations:run``, …). Uniform across
        # the bare and /api/v1 mounts.
        required = scope_for_request(path, request.method)
        if required and not scope_allows(principal.scopes, required):
            return principal, ({'error': f'Missing required scope: {required}'}, 403)
    elif request.method in _WRITE_METHODS:
        feature = feature_for_path(path)
        if feature and not principal.can(feature, 'write'):
            return principal, ({'error': 'Insufficient permissions'}, 403)

    return principal, None
