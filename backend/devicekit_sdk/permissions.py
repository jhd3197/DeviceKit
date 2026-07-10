"""Declaration-based permission gate for extensions (plan 03; port of ServerKit's
``plugins_sdk/permissions.py``).

This is NOT a sandbox — extensions run in-process with backend privileges (ServerKit ADR
0002). The gate makes privileged capability use *declared*: an extension must list a
capability in its manifest ``permissions`` before the SDK will let it use that capability.
Safety comes from the curated registry + consent card + pinned checksums, with the gate as
an honest guardrail against accidental undeclared use.
"""

# Host capabilities an extension may declare (mirrors extension_manifest.KNOWN_PERMISSIONS).
KNOWN_PERMISSIONS = {"adb", "device.control", "filesystem", "network", "llm"}


class PermissionDenied(PermissionError):
    """Raised when an extension uses a capability it did not declare in its manifest."""


def declared_permissions(slug):
    """The set of permissions the installed extension declared. Empty if not installed."""
    from devicekit_sdk import get_host
    host = get_host()
    if host is None:
        return set()
    row = host.get_extension(slug)
    if not row:
        return set()
    perms = row.get("permissions") or (row.get("manifest") or {}).get("permissions") or []
    if not isinstance(perms, list):
        return set()
    return {str(p) for p in perms}


def has(slug, capability):
    return capability in declared_permissions(slug)


def require(slug, capability):
    """Raise :class:`PermissionDenied` unless the extension declared ``capability``."""
    if not has(slug, capability):
        raise PermissionDenied(
            f"Extension '{slug}' has not declared the '{capability}' permission. "
            f"Add it to the extension.json \"permissions\" array.")
    return True


def unknown_permissions(permissions):
    """Permissions not recognized by the host — powers the consent UI's 'unknown' badge."""
    return [str(p) for p in (permissions or []) if str(p) not in KNOWN_PERMISSIONS]
