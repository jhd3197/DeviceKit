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


def _manifest(slug, backend, full=False):
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
            # Device-scoped extensions mount at /ext/<slug> and address devices as
            # /ext/<slug>/devices/<device_id>/<verb> (see docs/EXTENSIONS.md).
            "url_prefix": f"/ext/{slug}" if full else f"/extensions/{slug}",
            "step_types": "steps:register",
            "lifecycle": {"install": "lifecycle:on_install", "uninstall": "lifecycle:on_uninstall"},
        })
    if full:
        m.update({
            "permissions": ["device.control"],
            "models": "models:register",
            "ai_tools": "tools:register",
            "jobs": [{"kind": f"{_pkg(slug)}.poll", "handler": "jobs:poll"}],
            "schedules": [{
                "name": f"{slug}-poll", "kind": f"{_pkg(slug)}.poll",
                "interval_seconds": 60, "startup_delay_seconds": 15, "max_attempts": 1,
            }],
            "automation_templates": ["automations/example.json"],
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


_MODELS_TMPL = '''"""Data model for {slug}. Tables an extension owns MUST be named ``ext_<slug>_*``
(dashes -> underscores) so the host can create them at install and drop them on purge."""
from sqlalchemy import Table, Column, String, Float, Text

_TABLE_NAME = "ext_{pkg}_events"
_table = None


def register(db):
    """Called at activation. Defines the table on the shared metadata (idempotent)."""
    global _table
    md = db.Base.metadata
    if _TABLE_NAME in md.tables:
        _table = md.tables[_TABLE_NAME]
    else:
        _table = Table(
            _TABLE_NAME, md,
            Column("id", String, primary_key=True),
            Column("detail", Text),
            Column("created_at", Float),
        )
    return _table


def events_table():
    if _table is None:
        raise RuntimeError("events table not registered yet")
    return _table
'''

_TOOLS_TMPL = '''"""AI tools contributed by {slug} — bound namespaced as ``{pkg}__<name>`` into every
per-device Prompture ToolRegistry. Write tools are always routed through the confirmation
gate (plan 13); read tools run free."""


def register(ai):
    @ai.tool(is_write=False)
    def status() -> str:
        """Return a short status string for {title} (read-only example)."""
        return "{title} ready"
'''

_JOBS_TMPL = '''"""Background job handlers for {slug} (plan 05). The manifest ``jobs`` list maps a job
``kind`` to ``jobs:<func>``; the ``schedules`` list drives ``kind`` on an interval."""
import devicekit_sdk

log = devicekit_sdk.logger("{slug}")


def poll(job):
    """Periodic poll handler. ``job`` is a dict with ``payload``. Return a JSON-serializable
    summary (or raise to fail the tick)."""
    devices = devicekit_sdk.devices.list()
    log.info("{title} poll: %d device(s)", len(devices))
    return {{"polled": len(devices)}}
'''

_DEVICE_ROUTES_TMPL = '''"""Blueprint for {slug}, mounted at /ext/{slug}. Device-scoped routes follow the
convention /ext/{slug}/devices/<device_id>/<verb> (mirrors core device routes)."""
from flask import Blueprint, jsonify, request

import devicekit_sdk

SLUG = "{slug}"
bp = Blueprint("{pkg}", __name__)


@bp.route("/ping")
def ping():
    return jsonify({{"ok": True, "extension": SLUG}})


@bp.route("/devices/<device_id>/status")
def device_status(device_id):
    dev = devicekit_sdk.devices.get(device_id)
    if not dev:
        return jsonify({{"error": "device not found"}}), 404
    return jsonify({{"device_id": device_id, "ok": True}})
'''

_AUTOMATION_JSON_TMPL = '''{{
  "name": "{title} — example",
  "description": "Seeded by the {slug} extension. Edit or delete freely.",
  "steps": [
    {{ "type": "{pkg}.hello", "config": {{ "note": "hello from {slug}" }} }}
  ],
  "tags": ["{slug}"]
}}
'''


def cmd_scaffold(slug, backend, builtin, full=False):
    from devicekit.extension_manifest import SLUG_RE
    if not SLUG_RE.match(slug):
        print(f"[x] Invalid slug '{slug}' (allowed: {SLUG_RE.pattern})")
        return 1
    if full:
        backend = True
    base = os.path.join(_REPO_ROOT, "builtin-extensions", slug) if builtin else os.path.join(os.getcwd(), slug)
    if os.path.exists(base):
        print(f"[x] Refusing to overwrite existing {base}")
        return 1

    os.makedirs(base)
    with open(os.path.join(base, "extension.json"), "w", encoding="utf-8") as fh:
        json.dump(_manifest(slug, backend, full=full), fh, indent=2)

    files = ["extension.json"]
    if backend:
        bdir = os.path.join(base, "backend")
        os.makedirs(bdir)
        ctx = {"slug": slug, "pkg": _pkg(slug), "title": _title(slug)}
        open(os.path.join(bdir, "__init__.py"), "w").close()
        routes_tmpl = _DEVICE_ROUTES_TMPL if full else _ROUTES_TMPL
        backend_files = [("routes.py", routes_tmpl), ("steps.py", _STEPS_TMPL), ("lifecycle.py", _LIFECYCLE_TMPL)]
        if full:
            backend_files += [("models.py", _MODELS_TMPL), ("tools.py", _TOOLS_TMPL), ("jobs.py", _JOBS_TMPL)]
        for name, tmpl in backend_files:
            with open(os.path.join(bdir, name), "w", encoding="utf-8") as fh:
                fh.write(tmpl.format(**ctx))
        files += ["backend/__init__.py"] + [f"backend/{n}" for n, _ in backend_files]
        if full:
            adir = os.path.join(bdir, "automations")
            os.makedirs(adir)
            with open(os.path.join(adir, "example.json"), "w", encoding="utf-8") as fh:
                fh.write(_AUTOMATION_JSON_TMPL.format(**ctx))
            files += ["backend/automations/example.json"]

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
    parser.add_argument("--full", action="store_true",
                        help="rich device-scoped scaffold (models, ai_tools, jobs, schedules, "
                             "automation_templates, /ext/<slug> blueprint); implies --backend")
    parser.add_argument("--validate", metavar="PATH", help="validate an extension manifest and exit")
    args = parser.parse_args(argv)

    if args.validate:
        return cmd_validate(args.validate)
    if not args.slug:
        parser.print_help()
        return 2
    return cmd_scaffold(args.slug, args.backend, args.builtin, full=args.full)


if __name__ == "__main__":
    raise SystemExit(main())
