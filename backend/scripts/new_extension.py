#!/usr/bin/env python
"""Scaffold or validate a DeviceKit extension (plan 03 phase 4).

    python scripts/new_extension.py <slug> [--backend] [--builtin]
    python scripts/new_extension.py --validate <path-to-extension-dir-or-json>

``--validate`` runs the SAME ``validate_manifest`` rules the installer enforces (imported
from ``devicekit.extension_manifest``), so the CLI and the install pipeline never drift.
Scaffold mode writes ``extension.json`` plus, with ``--backend``, a ``backend/`` package
wired to the SDK (blueprint + step type + lifecycle).
"""
import os
import re
import sys
import json
import argparse

# Make the backend package importable when run from repo root or backend/.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_REPO_ROOT = os.path.dirname(_BACKEND_DIR)


def _title(slug):
    return " ".join(p.capitalize() for p in re.split(r"[-_]", slug) if p)


def _pkg(slug):
    return slug.replace("-", "_")


def cmd_validate(target):
    from devicekit.extension_manifest import validate_manifest, ManifestError
    path = target
    if os.path.isdir(path):
        path = os.path.join(path, "extension.json")
    if not os.path.isfile(path):
        print(f"[x] No extension.json at {target}")
        return 1
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:
        print(f"[x] Could not parse {path}: {e}")
        return 1
    try:
        validate_manifest(manifest)
    except ManifestError as e:
        print(f"[x] {e}")
        return 1
    print(f"[ok] {manifest['name']} v{manifest['version']} — manifest valid")
    return 0


def _manifest(slug, backend):
    m = {
        "name": slug,
        "display_name": _title(slug),
        "version": "0.1.0",
        "category": "utility",
        "description": f"{_title(slug)} extension for DeviceKit.",
        "author": "",
        "permissions": [],
        "min_devicekit_version": "1.0.0",
    }
    if backend:
        m.update({
            "entry_point": "routes:bp",
            "url_prefix": f"/extensions/{slug}",
            "step_types": "steps:register",
            "lifecycle": {"install": "lifecycle:on_install", "uninstall": "lifecycle:on_uninstall"},
        })
    return m


_ROUTES_TMPL = '''"""Blueprint for {slug} (mounted at /extensions/{slug})."""
from flask import Blueprint, jsonify

bp = Blueprint("{pkg}", __name__)


@bp.route("/ping")
def ping():
    return jsonify({{"ok": True, "extension": "{slug}"}})
'''

_STEPS_TMPL = '''"""Automation step type contributed by {slug}. Gets full AutomationEditor UI for free."""


def _execute(client, config, device_id):
    # TODO: implement your step. `client` is the DeviceKit Client; use the SDK for anything host-side.
    return "{slug} step ran"


def register():
    return {{
        "{pkg}.hello": {{
            "label": "{title} Hello",
            "category": "{title}",
            "config": {{"note": {{"type": "text", "label": "Note", "required": False}}}},
            "execute": _execute,
        }}
    }}
'''

_LIFECYCLE_TMPL = '''"""Lifecycle hooks (best-effort; failures are logged and swallowed by the host)."""
import devicekit_sdk

log = devicekit_sdk.logger("{slug}")


def on_install(client):
    log.info("{title} installed.")


def on_uninstall(client, purge=False):
    log.info(f"{title} uninstalled (purge={{purge}}).")
'''


def cmd_scaffold(slug, backend, builtin):
    from devicekit.extension_manifest import SLUG_RE
    if not SLUG_RE.match(slug):
        print(f"[x] Invalid slug '{slug}' (allowed: {SLUG_RE.pattern})")
        return 1
    base = os.path.join(_REPO_ROOT, "builtin-extensions", slug) if builtin else os.path.join(os.getcwd(), slug)
    if os.path.exists(base):
        print(f"[x] Refusing to overwrite existing {base}")
        return 1

    os.makedirs(base)
    with open(os.path.join(base, "extension.json"), "w", encoding="utf-8") as fh:
        json.dump(_manifest(slug, backend), fh, indent=2)

    files = ["extension.json"]
    if backend:
        bdir = os.path.join(base, "backend")
        os.makedirs(bdir)
        ctx = {"slug": slug, "pkg": _pkg(slug), "title": _title(slug)}
        open(os.path.join(bdir, "__init__.py"), "w").close()
        for name, tmpl in (("routes.py", _ROUTES_TMPL), ("steps.py", _STEPS_TMPL), ("lifecycle.py", _LIFECYCLE_TMPL)):
            with open(os.path.join(bdir, name), "w", encoding="utf-8") as fh:
                fh.write(tmpl.format(**ctx))
        files += [f"backend/{n}" for n in ("__init__.py", "routes.py", "steps.py", "lifecycle.py")]

    print(f"[ok] Scaffolded '{slug}' at {base}")
    for f in files:
        print(f"     {f}")
    if builtin:
        print("\nNext: install it through the real pipeline —")
        print(f'     curl -X POST localhost:5050/extensions/install -d \'{{"slug": "{slug}"}}\'  (bundled)')
    else:
        print("\nNext: install it through the real pipeline (dev loop) —")
        print(f'     curl -X POST localhost:5050/extensions/install-local -d \'{{"path": "{base}"}}\'')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scaffold or validate a DeviceKit extension")
    parser.add_argument("slug", nargs="?", help="extension slug to scaffold")
    parser.add_argument("--backend", action="store_true", help="include a backend/ package")
    parser.add_argument("--builtin", action="store_true", help="scaffold under builtin-extensions/")
    parser.add_argument("--validate", metavar="PATH", help="validate an extension manifest and exit")
    args = parser.parse_args(argv)

    if args.validate:
        return cmd_validate(args.validate)
    if not args.slug:
        parser.print_help()
        return 2
    return cmd_scaffold(args.slug, args.backend, args.builtin)


if __name__ == "__main__":
    raise SystemExit(main())
