"""The public-API scope layer (plan 21, part 1).

Owns the device-oriented scope catalog, the ``require_scope`` route decorator, and the
central path→scope table the auth gate consults for ``dk_`` key requests. The matching
semantics live in :func:`devicekit.services.principal._scope_allows` — one matcher shared
between the plan-20 key scopes and this surface, so ``devices:*`` / ``*`` wildcards and the
write-implies-narrower-verbs rule behave identically everywhere.

Design notes:

* ``require_scope`` is a **pass-through for session/user/solo/legacy principals** — the UI
  already passed the RBAC gate — and only enforces when the caller authenticated with a
  scoped ``dk_`` key (``principal.scopes is not None``). One endpoint serves UI + machines.
* Scope enforcement is uniform across the bare and ``/api/v1`` mounts: both hit the same
  handlers, so a key behaves the same wherever it knocks.
* The richer verbs are deliberate carve-outs: ``devices:command`` grants hardware-touching
  commands *without* general device writes; ``fleet:admin`` alone unlocks bulk/group
  actions (not implied by ``devices:write`` — fleet-wide blast radius is its own grant).
"""
from functools import wraps

from flask import g, jsonify

from devicekit.services.permissions import FEATURES
from devicekit.services.principal import _scope_allows, feature_for_path

API_V1_PREFIX = "/api/v1"

_WRITE_METHODS = ("POST", "PUT", "DELETE", "PATCH")

# Richer verbs beyond the plan-20 read/write pairs, keyed by feature. ``fleet`` is a
# pseudo-feature (its paths map to ``devices`` in the matrix) whose admin verb gates the
# bulk/group surface separately from single-device writes.
EXTRA_ACTIONS = {
    "devices": ("command",),
    "automations": ("run",),
    "extensions": ("admin",),
}
PSEUDO_FEATURES = {
    "fleet": ("admin",),
}

SCOPE_DESCRIPTIONS = {
    "*": "Full access to every feature (master key).",
    "devices:command": "Send commands to devices (tap/press/swipe/adb/reboot/files) without general device writes.",
    "automations:run": "Run or cancel automations without editing them.",
    "extensions:admin": "Install, remove, enable/disable, and configure extensions.",
    "fleet:admin": "Fleet groups and bulk actions (fleet-wide blast radius; never implied by devices:write).",
}
_ACTION_BLURBS = {
    "read": "Read {feature} state.",
    "write": "Create/update/delete {feature} (implies the feature's narrower verbs).",
}


def available_scopes():
    """The full catalog of assignable scope tokens (plan-20 pairs + plan-21 verbs)."""
    scopes = ["*"]
    for f in FEATURES:
        scopes.append(f"{f}:*")
        scopes.append(f"{f}:read")
        scopes.append(f"{f}:write")
        scopes.extend(f"{f}:{a}" for a in EXTRA_ACTIONS.get(f, ()))
    for f, actions in PSEUDO_FEATURES.items():
        scopes.append(f"{f}:*")
        scopes.extend(f"{f}:{a}" for a in actions)
    return scopes


def describe_scopes():
    """``[{'scope', 'description'}, ...]`` for the key-creation UI and ``/api/v1/scopes``."""
    out = []
    for scope in available_scopes():
        if scope in SCOPE_DESCRIPTIONS:
            desc = SCOPE_DESCRIPTIONS[scope]
        elif scope.endswith(":*"):
            desc = f"All actions on {scope[:-2]}."
        else:
            feature, action = scope.split(":", 1)
            desc = _ACTION_BLURBS.get(action, "").format(feature=feature)
        out.append({"scope": scope, "description": desc})
    return out


def strip_version(path):
    """Normalize a request path: ``/api/v1/devices`` → ``/devices``; bare paths unchanged."""
    if path == API_V1_PREFIX:
        return "/"
    if path.startswith(API_V1_PREFIX + "/"):
        return path[len(API_V1_PREFIX):]
    return path


def scope_allows(scopes, required):
    """Whether a key's scope list satisfies a ``feature:action`` requirement (shared matcher)."""
    feature, _, action = required.partition(":")
    return _scope_allows(scopes, feature, action)


# Paths whose writes need a richer verb than ``<feature>:write``. Checked before the
# feature fallback; ``path`` is already version-stripped. Order: most specific first.
_COMMAND_SEGMENTS = ("/adb", "/reboot", "/tap", "/press", "/swipe", "/files")


def scope_for_request(path, method):
    """The scope a ``dk_`` key must hold for this request, or ``None`` (auth-only path).

    Reads need ``<feature>:read``; writes the catalog verb for the path — the richer
    carve-outs (``devices:command``, ``automations:run``, ``extensions:admin``,
    ``fleet:admin``) where they apply, else ``<feature>:write``.
    """
    write = method in _WRITE_METHODS
    if write:
        # Read-shaped POST: validating an FQL expression mutates nothing.
        if path == "/fleet/query/validate":
            return "devices:read"
        if path.startswith("/fleet/groups") or path.startswith("/fleet/query/bulk-action"):
            return "fleet:admin"
        if path.startswith("/devices/") and any(seg in path for seg in _COMMAND_SEGMENTS):
            return "devices:command"
        if path.startswith("/automations/") and (path.endswith("/run") or path.endswith("/cancel")):
            return "automations:run"
        if path.startswith("/extensions"):
            return "extensions:admin"
    feature = feature_for_path(path)
    if not feature:
        return None
    return f"{feature}:{'write' if write else 'read'}"


def require_scope(scope):
    """Gate a route on ``scope`` — but only for scoped ``dk_`` keys.

    Session/user/solo/legacy principals pass straight through (they already cleared the
    plan-20 gate), so one handler serves the UI and machines. The required scope is stamped
    on the view (``_dk_scope``) for the OpenAPI generator to document.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            principal = getattr(g, "principal", None)
            if principal is not None and getattr(principal, "scopes", None) is not None \
                    and not getattr(principal, "full_access", False):
                if not scope_allows(principal.scopes, scope):
                    return jsonify({"error": f"Missing required scope: {scope}"}), 403
            return view(*args, **kwargs)
        wrapper._dk_scope = scope
        return wrapper
    return decorator
