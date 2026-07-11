"""Extension manifest spec, validator, and archive-safety helpers (plan 03).

Ports ServerKit's ``_validate_manifest`` / ``_safe_extract_path`` (see
``plugin_service.py``) and adapts them to DeviceKit's contribution points. The rules here
are the single source of truth mirrored by ``GET /extensions/manifest-spec``, the
scaffolding CLI's ``--validate`` mode (plan 04), and ``docs/EXTENSIONS.md``.
"""
import os
import re

# Current DeviceKit platform version — extensions gate against this via
# ``min_devicekit_version`` / ``max_devicekit_version``.
from devicekit import __version__ as DEVICEKIT_VERSION


class ManifestError(ValueError):
    """Raised when an extension manifest fails validation."""


# Slug rule for the manifest ``name`` — matches ServerKit: alphanumerics, dashes,
# underscores. (The registry index uses a stricter kebab-case rule; the two must agree
# per-extension but the validators differ.)
SLUG_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

# "module.path:attr" reference used by entry_point, models, lifecycle, step_types, etc.
MODULE_REF_RE = re.compile(r'^[A-Za-z_][\w.]*:[A-Za-z_]\w*$')

# Loose semver: MAJOR.MINOR[.PATCH][-/.pre]
SEMVER_RE = re.compile(r'^\d+\.\d+(\.\d+)?([.-][0-9A-Za-z.-]+)?$')

CATEGORIES = {"automation", "monitoring", "integration", "ai", "utility"}

# Host capabilities an extension may declare. Enforced at call time by the SDK permission
# gate (declaration-based, not a sandbox — see plan 03 / ServerKit ADR 0002).
KNOWN_PERMISSIONS = {"adb", "device.control", "filesystem", "network", "llm"}

# Contribution kinds and the keys each entry must carry (frontend wiring, plan 04).
REQUIRED_CONTRIB_KEYS = {
    "nav": ("label", "route"),
    "routes": ("path", "component"),
    "widgets": ("slot", "component"),
    "command_palette": ("label", "action"),
}
KNOWN_CONTRIB_KINDS = set(REQUIRED_CONTRIB_KEYS) | {"page_titles"}

REQUIRED_FIELDS = ("name", "display_name", "version")


def _is_module_ref(value):
    return isinstance(value, str) and bool(MODULE_REF_RE.match(value))


def validate_manifest(manifest):
    """Validate an extension manifest. Returns ``True`` or raises :class:`ManifestError`.

    Hard failures (missing required fields, bad slug) raise immediately. Everything else is
    accumulated into a single ``problems`` list so an author sees all shape errors at once.
    Unknown contribution kinds are tolerated (forward-compat) — they do not fail validation.
    """
    if not isinstance(manifest, dict):
        raise ManifestError("Manifest must be a JSON object")

    missing = [f for f in REQUIRED_FIELDS if not manifest.get(f)]
    if missing:
        raise ManifestError(f"Manifest missing required fields: {', '.join(missing)}")

    name = manifest["name"]
    if not isinstance(name, str) or not SLUG_RE.match(name):
        raise ManifestError(
            f"Extension name must be alphanumeric/dashes/underscores: {name!r}")

    problems = []

    version = manifest["version"]
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        problems.append(f"version must be semver (e.g. 1.0.0), got {version!r}")

    category = manifest.get("category", "utility")
    if category not in CATEGORIES:
        problems.append(f"category must be one of {sorted(CATEGORIES)}, got {category!r}")

    perms = manifest.get("permissions", [])
    if not isinstance(perms, list):
        problems.append("permissions must be a list")
    else:
        unknown = [p for p in perms if p not in KNOWN_PERMISSIONS]
        if unknown:
            problems.append(
                f"unknown permissions {unknown} (known: {sorted(KNOWN_PERMISSIONS)})")

    # module:attr references
    for field in ("entry_point", "models", "step_types", "fql_fields", "ai_tools"):
        val = manifest.get(field)
        if val is not None and not _is_module_ref(val):
            problems.append(f"{field} must be a 'module:attr' string (got {val!r})")

    lifecycle = manifest.get("lifecycle")
    if lifecycle is not None:
        if not isinstance(lifecycle, dict):
            problems.append("lifecycle must be an object of phase -> 'module:func'")
        else:
            for phase, ref in lifecycle.items():
                if not _is_module_ref(ref):
                    problems.append(f"lifecycle.{phase} must be 'module:func' (got {ref!r})")

    jobs = manifest.get("jobs")
    if jobs is not None:
        if not isinstance(jobs, list):
            problems.append("jobs must be a list")
        else:
            for i, job in enumerate(jobs):
                if not isinstance(job, dict) or "kind" not in job or not _is_module_ref(job.get("handler", "")):
                    problems.append(f"jobs[{i}] must be {{kind, handler: 'module:func'}}")

    schedules = manifest.get("schedules")
    if schedules is not None:
        if not isinstance(schedules, list):
            problems.append("schedules must be a list")
        else:
            for i, sch in enumerate(schedules):
                if not isinstance(sch, dict) or "name" not in sch or "kind" not in sch:
                    problems.append(f"schedules[{i}] needs name and kind")

    config_schema = manifest.get("config_schema")
    if config_schema is not None and not isinstance(config_schema, dict):
        problems.append("config_schema must be an object of field -> spec")

    templates = manifest.get("automation_templates")
    if templates is not None and not isinstance(templates, list):
        problems.append("automation_templates must be a list of paths")

    url_prefix = manifest.get("url_prefix")
    if url_prefix is not None and (not isinstance(url_prefix, str) or not url_prefix.startswith("/")):
        problems.append("url_prefix must be a string starting with '/'")

    contributions = manifest.get("contributions")
    if contributions is not None:
        if not isinstance(contributions, dict):
            problems.append("contributions must be an object")
        else:
            for kind, entries in contributions.items():
                if kind not in KNOWN_CONTRIB_KINDS:
                    continue  # forward-compat: unknown kinds tolerated
                if kind == "page_titles":
                    if not isinstance(entries, dict):
                        problems.append("contributions.page_titles must be an object of path -> title")
                    continue
                required = REQUIRED_CONTRIB_KEYS[kind]
                if not isinstance(entries, list):
                    problems.append(f"contributions.{kind} must be a list")
                    continue
                for i, entry in enumerate(entries):
                    if not isinstance(entry, dict) or any(k not in entry for k in required):
                        problems.append(f"contributions.{kind}[{i}] missing {', '.join(required)}")

    if problems:
        raise ManifestError(
            "Manifest validation failed: " + "; ".join(problems)
            + ". See GET /extensions/manifest-spec or docs/EXTENSIONS.md.")
    return True


def safe_extract_path(dest_root, rel_path):
    """Zip-Slip defense (verbatim port of ServerKit ``_safe_extract_path``).

    Rejects empty paths, absolute paths / drive letters, ``..`` traversal, and any entry
    that would escape ``dest_root``. Returns the validated absolute destination path.
    """
    if not rel_path:
        raise ValueError("empty path in archive")
    normalized = rel_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("/") or ":" in normalized.split("/")[0]:
        raise ValueError(f"absolute path in archive: {rel_path!r}")
    if ".." in normalized.split("/"):
        raise ValueError(f"path traversal in archive: {rel_path!r}")
    out = os.path.normpath(os.path.join(dest_root, normalized))
    root = os.path.normpath(dest_root) + os.sep
    if not (out + os.sep).startswith(root):
        raise ValueError(f"archive entry escapes destination: {rel_path!r}")
    return out


def table_prefix(slug):
    """The ``ext_<slug>_`` prefix that an extension's data tables MUST use (dashes ->
    underscores so it is a valid SQL identifier)."""
    return f"ext_{slug.replace('-', '_')}_"


def _parse_version(v):
    parts = re.split(r'[.-]', str(v))
    nums = []
    for p in parts:
        if p.isdigit():
            nums.append(int(p))
        else:
            break
    return tuple(nums) if nums else (0,)


def version_satisfies(current, minimum=None, maximum=None):
    """True if ``current`` is within [minimum, maximum] (inclusive; either may be None)."""
    cur = _parse_version(current)
    if minimum and cur < _parse_version(minimum):
        return False
    if maximum and cur > _parse_version(maximum):
        return False
    return True


def assert_devicekit_compatible(manifest):
    """Raise :class:`ManifestError` if the manifest's version gate excludes this DeviceKit."""
    minv = manifest.get("min_devicekit_version")
    maxv = manifest.get("max_devicekit_version")
    if (minv or maxv) and not version_satisfies(DEVICEKIT_VERSION, minv, maxv):
        raise ManifestError(
            f"{manifest.get('display_name') or manifest['name']} v{manifest['version']} "
            f"needs DeviceKit {minv or '*'}–{maxv or '*'} (this is {DEVICEKIT_VERSION}).")


def manifest_spec():
    """Machine-readable description of the manifest surface for ``GET /extensions/manifest-spec``."""
    return {
        "required_fields": list(REQUIRED_FIELDS),
        "slug_pattern": SLUG_RE.pattern,
        "module_ref_pattern": MODULE_REF_RE.pattern,
        "categories": sorted(CATEGORIES),
        "known_permissions": sorted(KNOWN_PERMISSIONS),
        "contribution_kinds": {k: list(v) for k, v in REQUIRED_CONTRIB_KEYS.items()},
        "contribution_points": {
            "entry_point": "module:blueprint under devicekit.extensions.<slug>.*",
            "url_prefix": "default /extensions/<slug>",
            "models": "module:func — tables MUST be named ext_<slug>_*",
            "step_types": "module:func returning {type_name: {label, category, config, execute}}",
            "fql_fields": "module:func returning {field_name: spec}",
            "ai_tools": "module:func registering Prompture tools (namespaced <slug>__<name>)",
            "lifecycle": "{install: 'module:func', uninstall: 'module:func'}",
            "jobs": "[{kind, handler: 'module:func'}]",
            "schedules": "[{name, kind, interval_seconds}]",
            "config_schema": "{field: {type, secret}}",
            "automation_templates": "[relative/path.json]",
            "contributions": "{nav, routes, widgets, command_palette, page_titles}",
        },
        "devicekit_version": DEVICEKIT_VERSION,
    }
