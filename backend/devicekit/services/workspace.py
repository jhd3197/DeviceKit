"""Workspace scoping policy (plan 20, part 4) — the crown jewel ported from ServerKit.

The whole retrofit turns on one idea: **opt-in, narrow-only scoping**. With no workspace context
on the request, every query is unchanged — byte-for-byte the old single-tenant behavior. Nothing
scopes until someone activates a workspace (``X-Workspace-Id``).

Two hard rules run through the model: workspace/grant roles only NARROW, never elevate beyond the
global role; and visibility ≠ permission (a grant lets you *see* a resource, not do more to it).
"""

# Membership roles as an ordered tier — highest wins when a user reaches a resource by more than
# one path (direct membership, a grant, …).
WORKSPACE_ROLES = ("viewer", "member", "admin", "owner")
_RANK = {role: i for i, role in enumerate(WORKSPACE_ROLES)}

GRANT_LEVELS = ("viewer", "editor")

# Device danger tiers → the minimum workspace role that may perform them. Fleet-wide and raw
# shell/ADB are intentionally absent: those are platform-admin only, never unlockable by a
# workspace role (see ``PLATFORM_ADMIN_ONLY``).
DEVICE_ACTION_TIERS = {
    "read_metrics": "viewer",
    "run_automation": "member",
    "send_command": "member",
    "factory_reset": "admin",
    "uninstall_agent": "admin",
    "delete_device": "admin",
}

# Actions no workspace role can ever authorize — only a platform admin (global admin / full access).
PLATFORM_ADMIN_ONLY = ("fleet_wide", "raw_shell", "raw_adb")


def role_rank(role):
    return _RANK.get(role, -1)


def highest(roles):
    """The highest-tier role among several paths to a resource. ``None`` if none apply."""
    best, best_rank = None, -1
    for role in roles:
        r = role_rank(role)
        if r > best_rank:
            best, best_rank = role, r
    return best


def role_satisfies(role, min_role):
    """Whether ``role`` meets or exceeds ``min_role`` in the tier."""
    return role_rank(role) >= role_rank(min_role) >= 0


def resolve_workspace_id(request):
    """Extract the requested workspace id from ``X-Workspace-Id`` (header or query param).

    Deliberately lenient: this only *reads* the header. Whether that workspace exists and whether
    the principal may use it is decided later — an unknown/forbidden value degrades to "no
    scoping", never an error."""
    if request is None:
        return None
    wid = request.headers.get("X-Workspace-Id") if hasattr(request, "headers") else None
    if not wid and hasattr(request, "args"):
        wid = request.args.get("workspace_id")
    return (wid or "").strip() or None


def scope_query(query, model, workspace_id):
    """Centralized narrow-only filter. With no workspace context the query is returned unchanged;
    with one, it is narrowed to rows in that workspace. Only meaningful for models that carry a
    ``workspace_id`` column (the born-in-workspace resources)."""
    if not workspace_id:
        return query
    if not hasattr(model, "workspace_id"):
        return query
    return query.filter(model.workspace_id == workspace_id)
