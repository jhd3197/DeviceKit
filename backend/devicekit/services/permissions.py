"""Global role + per-feature read/write permission matrix (plan 20, part 1).

DeviceKit's authorization has two independent axes:

* the **global role** (``admin`` / ``operator`` / ``viewer``) — the ceiling on what a user can
  ever do, and
* an optional **per-user JSON override** that NARROWS the role's template feature-by-feature.

Resolution: ``admin`` short-circuits to everything; otherwise the role template is the base and
a validated override replaces per-feature entries. Two invariants run through the whole stack
(and are re-asserted in plan 20's workspace layer): overrides only narrow — they can never grant
a feature the role template denies — and ``write`` always implies ``read``.
"""

# The feature axis DeviceKit gates on. Kept deliberately small; each maps to a family of routes
# (see ``feature_for_path`` in ``principal.py``).
FEATURES = (
    "devices",        # device registry, state, control
    "automations",    # automations, profiles, pipeline
    "extensions",     # extension platform install/config
    "commands",       # AI-agent control + command dispatch
    "metrics",        # metrics history + alert rules
    "notifications",  # notification center + channels
    "settings",       # durable app settings + user management
    "agents",         # agent enrollment / fleet registry
)

ROLES = ("admin", "operator", "viewer")

_ALL = {f: {"read": True, "write": True} for f in FEATURES}


def _template(read_features, write_features):
    return {
        f: {"read": f in read_features, "write": f in write_features}
        for f in FEATURES
    }


# Role templates. A *viewer* sees fleet state; an *operator* also runs automations and sends
# benign commands and manages notification prefs; an *admin* manages everything.
ROLE_PERMISSION_TEMPLATES = {
    "admin": dict(_ALL),
    "operator": _template(
        read_features=set(FEATURES),
        write_features={"automations", "commands", "notifications"},
    ),
    "viewer": _template(
        read_features={"devices", "automations", "extensions", "metrics", "notifications"},
        write_features=set(),
    ),
}


class PermissionError(ValueError):
    """Raised when a per-user override is malformed or tries to elevate beyond the role."""


def validate_overrides(overrides, role):
    """Validate + normalize a per-user override map, enforcing narrow-only + write⇒read.

    Returns a clean ``{feature: {read, write}}`` dict (only the features the caller specified).
    Raises ``PermissionError`` on an unknown feature, a bad shape, a ``write`` without ``read``,
    or an entry that grants a permission the role template denies (elevation).
    """
    if overrides in (None, {}):
        return {}
    if not isinstance(overrides, dict):
        raise PermissionError("permissions override must be an object")

    ceiling = ROLE_PERMISSION_TEMPLATES.get(role, ROLE_PERMISSION_TEMPLATES["viewer"])
    clean = {}
    for feature, perms in overrides.items():
        if feature not in FEATURES:
            raise PermissionError(f"unknown feature: {feature}")
        if not isinstance(perms, dict):
            raise PermissionError(f"permissions for {feature} must be an object")
        read = bool(perms.get("read", False))
        write = bool(perms.get("write", False))
        if write and not read:
            raise PermissionError(f"{feature}: write implies read")
        # Narrow-only: an override may not grant what the role template withholds. (admin's
        # template grants everything, so admins are never blocked here.)
        cap = ceiling[feature]
        if (read and not cap["read"]) or (write and not cap["write"]):
            raise PermissionError(f"{feature}: override cannot exceed the '{role}' role")
        clean[feature] = {"read": read, "write": write}
    return clean


def resolve_permissions(role, overrides=None):
    """The effective ``{feature: {read, write}}`` matrix for a user.

    ``admin`` is always full access. Otherwise the role template is the base and a validated
    override replaces individual feature entries.
    """
    if role == "admin":
        return {f: dict(v) for f, v in _ALL.items()}
    base = {f: dict(v) for f, v in ROLE_PERMISSION_TEMPLATES.get(
        role, ROLE_PERMISSION_TEMPLATES["viewer"]).items()}
    for feature, perms in validate_overrides(overrides, role).items():
        base[feature] = perms
    return base


def can(permissions, feature, action):
    """Check one resolved matrix. Unknown feature/action → denied."""
    return bool(permissions.get(feature, {}).get(action, False))
