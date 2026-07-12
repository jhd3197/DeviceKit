"""Auto-generated OpenAPI 3.0 spec for the public ``/api/v1`` surface (plan 21, part 2).

No hand-maintained spec file: the generator walks the Flask ``url_map`` the same way
ServerKit's ``openapi_service`` does — blueprint name → tag, view docstring → summary and
description, path converters → parameters. Only the versioned mirror (``v1_*`` endpoints,
plus the ``api_v1`` meta blueprint) is documented; the bare mount is the same handlers at
legacy paths, so documenting it twice would only add noise.

Both auth schemes are declared: ``ApiKeyAuth`` (the ``X-API-Key: dk_…`` machine header) and
``BearerAuth`` (the UI's session token). Routes decorated with ``require_scope`` advertise
their scope in ``x-required-scope`` and in the description, so an integrator can mint a
minimal key straight from the docs page.
"""

# Paths (version-stripped) reachable without credentials — mirrors the gate's PUBLIC_PATHS.
_PUBLIC = ('/health', '/auth/login', '/auth/logout', '/auth/session')

# Werkzeug converter class name → OpenAPI schema type.
_CONVERTER_TYPES = {
    'IntegerConverter': {'type': 'integer'},
    'FloatConverter': {'type': 'number'},
    'UUIDConverter': {'type': 'string', 'format': 'uuid'},
    'PathConverter': {'type': 'string'},
}

_ERROR_RESPONSES = {
    '401': {'description': 'Authentication required',
            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}},
    '403': {'description': 'Insufficient permissions or missing key scope',
            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}},
}


def _required_scope(view):
    """The ``require_scope`` stamp, walking wrapper chains other decorators may add."""
    seen = set()
    while view is not None and id(view) not in seen:
        seen.add(id(view))
        scope = getattr(view, '_dk_scope', None)
        if scope:
            return scope
        view = getattr(view, '__wrapped__', None)
    return None


def _docstring_parts(view):
    doc = (view.__doc__ or '').strip()
    if not doc:
        return '', ''
    lines = doc.splitlines()
    summary = lines[0].strip()
    description = '\n'.join(line.strip() for line in lines[1:]).strip()
    return summary, description


def _openapi_path(rule):
    """``/api/v1/devices/<device_id>`` → ``/api/v1/devices/{device_id}``."""
    path = rule.rule
    for arg in rule.arguments:
        for marker in (f'<{arg}>',):
            path = path.replace(marker, f'{{{arg}}}')
        # Typed converters: <int:arg>, <path:arg>, ...
        start = path.find(':' + arg + '>')
        if start != -1:
            open_idx = path.rfind('<', 0, start)
            path = path[:open_idx] + f'{{{arg}}}' + path[start + len(arg) + 2:]
    return path


def _parameters(rule):
    params = []
    converters = getattr(rule, '_converters', {}) or {}
    for arg in sorted(rule.arguments):
        conv = converters.get(arg)
        schema = _CONVERTER_TYPES.get(type(conv).__name__, {'type': 'string'}) if conv \
            else {'type': 'string'}
        params.append({'name': arg, 'in': 'path', 'required': True, 'schema': dict(schema)})
    return params


def generate_openapi(app):
    """Build the OpenAPI 3.0 document for the ``/api/v1`` mirror from the live url_map."""
    paths = {}
    tags = set()
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint == 'static':
            continue
        if endpoint.startswith('v1_'):
            tag = endpoint.split('.', 1)[0][len('v1_'):]
        elif endpoint.startswith('api_v1.'):
            tag = 'meta'
        else:
            continue  # bare mount / extension blueprints: not part of the versioned surface
        view = app.view_functions.get(endpoint)
        if view is None:
            continue
        tags.add(tag)
        summary, description = _docstring_parts(view)
        scope = _required_scope(view)
        stripped = rule.rule[len('/api/v1'):] if rule.rule.startswith('/api/v1') else rule.rule
        public = stripped in _PUBLIC
        path = _openapi_path(rule)
        item = paths.setdefault(path, {})
        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            op = {
                'tags': [tag],
                'summary': summary or f'{method} {path}',
                'operationId': f"{method.lower()}_{endpoint.replace('.', '_')}",
                'responses': {
                    '200': {'description': 'Success',
                            'content': {'application/json': {'schema': {'type': 'object'}}}},
                    **({} if public else _ERROR_RESPONSES),
                },
            }
            if description:
                op['description'] = description
            if _parameters(rule):
                op['parameters'] = _parameters(rule)
            if method in ('POST', 'PUT', 'PATCH'):
                op['requestBody'] = {'required': False, 'content': {
                    'application/json': {'schema': {'type': 'object'}}}}
            if public:
                op['security'] = []
            if scope:
                op['x-required-scope'] = scope
                note = f'Requires scope `{scope}` when authenticated with a `dk_` API key.'
                op['description'] = f"{op.get('description', '')}\n\n{note}".strip()
            item[method.lower()] = op

    return {
        'openapi': '3.0.3',
        'info': {
            'title': 'DeviceKit Public API',
            'version': 'v1',
            'description': (
                'Versioned, scope-gated API over the DeviceKit fleet. Dual auth: the UI uses '
                'session tokens (BearerAuth), machines use scoped `dk_` keys (ApiKeyAuth). '
                'Write endpoints may additionally require a catalog verb such as '
                '`devices:command` or `automations:run` — see `x-required-scope` per operation '
                'and `GET /api/v1/scopes` for the catalog.'
            ),
        },
        'servers': [{'url': '/'}],
        'tags': [{'name': t} for t in sorted(tags)],
        'paths': {p: paths[p] for p in sorted(paths)},
        'components': {
            'securitySchemes': {
                'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key',
                               'description': 'Scoped machine key (`dk_…`), created under Settings → API Keys.'},
                'BearerAuth': {'type': 'http', 'scheme': 'bearer',
                               'description': 'UI session token (also accepted via `X-Session-Token`).'},
            },
            'schemas': {
                'Error': {'type': 'object',
                          'properties': {'error': {'type': 'string'}},
                          'required': ['error']},
            },
        },
        'security': [{'ApiKeyAuth': []}, {'BearerAuth': []}],
    }
