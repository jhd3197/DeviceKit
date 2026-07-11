"""The request principal — who (or what) is behind the current request (plan 20).

Every gated request resolves to exactly one ``Principal``, attached to ``flask.g.principal`` by
the auth gate. It unifies the identities DeviceKit now understands:

* ``solo``   — auth disabled + no real users yet: the historical full-access single user.
* ``legacy`` — the pre-plan-20 global ``API_KEY`` (full access, kept for back-compat).
* ``user``   — a logged-in ``User`` (role + resolved permission matrix).
* ``apikey`` — a hashed scoped ``dk_`` key (plan 20 part 2; scopes gate instead of the matrix).
* ``agent``  — the machine axis (``X-Agent-Token``); orthogonal to human RBAC.
* ``anonymous`` — public endpoints (health/login); never authorized for anything gated.

``full_access`` principals (solo/legacy/admin) bypass the feature matrix entirely.
"""
from dataclasses import dataclass, field

from devicekit.services.permissions import can


@dataclass
class Principal:
    kind: str
    user_id: str = None
    username: str = None
    role: str = None
    permissions: dict = field(default_factory=dict)   # resolved {feature: {read, write}}
    full_access: bool = False                          # bypass the matrix (solo/legacy/admin)
    api_key_id: str = None
    scopes: list = None                                # plan 20 part 2 (dk_ key scopes)
    workspace_id: str = None                           # plan 20 part 4 (active tenant)

    @property
    def is_admin(self):
        return self.full_access or self.role == "admin"

    @property
    def is_authenticated(self):
        return self.kind not in ("anonymous",)

    def can(self, feature, action):
        """Authorize ``action`` (read|write) on ``feature`` for this principal."""
        if self.full_access:
            return True
        if self.scopes is not None:
            # A scoped key authorizes via its scope list, not the role matrix.
            return _scope_allows(self.scopes, feature, action)
        return can(self.permissions, feature, action)

    def to_dict(self):
        return {
            "kind": self.kind,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "permissions": self.permissions or {},
            "full_access": self.full_access,
            "is_admin": self.is_admin,
            "workspace_id": self.workspace_id,
            "scopes": self.scopes,
        }


def _scope_allows(scopes, feature, action):
    """Wildcard scope matching (plan 20 part 2). ``devices:*`` ⇒ ``devices:read``; ``*`` ⇒ all."""
    wanted = f"{feature}:{action}"
    for scope in scopes or []:
        if scope in ("*", "*:*", wanted, f"{feature}:*"):
            return True
    return False


# --- path → feature mapping for the write gate --------------------------------------------
# Longest-prefix-wins: order most-specific first. A path with no match is not feature-gated
# (it still requires an authenticated principal) so niche endpoints keep working while the
# matrix governs the main resource families.
_PATH_FEATURES = (
    ("/agent-devices", "agents"),
    ("/enrollment", "agents"),
    ("/pairing", "agents"),
    ("/device-commands", "devices"),
    ("/devices", "devices"),
    ("/dashboard", "devices"),
    ("/fleet", "devices"),
    ("/agent/", "commands"),
    ("/automations", "automations"),
    ("/profiles", "automations"),
    ("/pipeline", "automations"),
    ("/extensions", "extensions"),
    ("/ext/", "extensions"),
    ("/metrics", "metrics"),
    ("/notifications", "notifications"),
    ("/settings", "settings"),
    ("/config", "settings"),
    ("/vault", "settings"),
    ("/secrets", "settings"),
    ("/workspaces", "settings"),
    ("/api-keys", "settings"),
    ("/users", "settings"),
    ("/audit", "settings"),
)


def feature_for_path(path):
    """Return the feature a request path belongs to, or ``None`` if unmapped.

    First match wins, so ``_PATH_FEATURES`` lists the more-specific prefixes first
    (``/agent-devices`` before ``/agent/``, ``/device-commands`` before ``/devices``).
    """
    for prefix, feature in _PATH_FEATURES:
        if path.startswith(prefix):
            return feature
    return None
