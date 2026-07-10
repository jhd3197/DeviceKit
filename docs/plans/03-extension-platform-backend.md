# Plan 03 — Extension Platform: Backend

**Status:** ✅ shipped (2026-07-10) — all four phases landed. Backend-only (frontend
marketplace is plan 04). One deviation: the first builtin is a genuinely useful
self-contained extension (`devicekit-webhook-notify`) rather than a destructive extraction
of core visual-regression — it exercises every contribution seam (step type, AI tool,
blueprint, `ext_*` table, secret config, lifecycle) while keeping core + all tests green.
Migrating core visual-regression into an extension is a documented follow-up.
**Inspired by:** ServerKit's plugin system — `backend/app/services/plugin_service.py`,
`backend/app/plugins_sdk/`, `backend/app/services/extension_lifecycle.py`,
`docs/EXTENSIONS.md`, ADRs 0001/0002, and the `serverkit-extensions` registry repo
**Depends on:** 01 (installed-extension rows must survive restarts), 02 (extension routes mount as blueprints)

This is the centerpiece plan. ServerKit and DeviceKit are both Flask, so the mechanism
ports almost directly — the interesting work is choosing DeviceKit's contribution
points, which are unusually good.

## Concept

An extension is a zip/folder: `extension.json` manifest + optional `backend/` package +
optional `frontend/` module (plan 04). Extensions are installed from a curated registry,
a GitHub URL, an upload, or a local path — all through one pipeline with a
preview/consent step and a pinned sha256. Backend halves hot-load into the running app.

## Manifest (`extension.json`)

Adapted from ServerKit's `plugin.json` (see `_validate_manifest()` in
`plugin_service.py:344` and `builtin-extensions/serverkit-mail/plugin.json` for the
fullest example):

```jsonc
{
  "name": "devicekit-appium",            // slug, ^[a-zA-Z0-9_-]+$
  "display_name": "Appium Bridge",
  "version": "1.0.0",                     // semver
  "category": "automation",               // automation|monitoring|integration|ai|utility
  "permissions": ["adb", "device.control", "filesystem", "network", "llm"],
  "min_devicekit_version": "0.9.0",

  // Backend wiring
  "entry_point": "routes:bp",            // module:blueprint under extensions.<slug>.*
  "url_prefix": "/extensions/appium",    // default /extensions/<slug>
  "models": "models:register",           // tables MUST be named ext_<slug>_*
  "lifecycle": { "install": "lifecycle:on_install", "uninstall": "lifecycle:on_uninstall" },
  "jobs": [{ "kind": "appium.session.reap", "handler": "jobs:reap" }],       // plan 05
  "schedules": [{ "name": "reap-hourly", "kind": "appium.session.reap", "interval_seconds": 3600 }],
  "config_schema": { "server_url": { "type": "string", "secret": false } },

  // DeviceKit-specific contribution points (the differentiators)
  "step_types": "steps:register",        // returns {type_name: {label, category, config, execute}}
  "fql_fields": "fql:register",          // returns {field_name: spec} merged into SUPPORTED_FIELDS
  "ai_tools": "tools:register",          // Prompture ToolRegistry registrations (plan 13 gates writes)
  "automation_templates": ["templates/smoke-test.json"],  // importable via existing export/import

  // Frontend wiring (plan 04)
  "contributions": { "nav": [], "routes": [], "widgets": [], "command_palette": [] }
}
```

### Why DeviceKit's contribution points are special

- **`step_types` is the killer feature.** The `AutomationEditor` already auto-renders
  config forms from `GET /automations/step-types` (`api_app.py:859`) — an extension
  contributing a step type gets full editor UI **with zero frontend code**. ServerKit
  has no equivalent; this makes useful DeviceKit extensions much cheaper to write.
  Prerequisite refactor: execution today is an `elif` chain in `_execute_step`
  (`automation.py:382`) — convert `STEP_TYPES` (`automation.py:10`) into a dispatch
  registry whose entries carry an `execute` callable, so core and extension steps run
  through one path and extensions can't require editing core.
- `fql_fields` extends `SUPPORTED_FIELDS` in `fleet_query.py` — extensions make their
  data queryable (`appium.session_count > 0`).
- `ai_tools` plugs into the existing Prompture `ToolRegistry`
  (`prompture_agent.py:build_device_tools`), namespaced `<slug>__<name>`
  (double-underscore, not dots — provider function-name limits).

Candidate first extensions to validate the design: Appium bridge, Scrcpy integration,
Maestro flow runner, Firebase Test Lab exporter, Slack/Discord notifier (plan 06
channel), app-install/APK-library manager.

## Install pipeline (port of `_install_from_buffer()`)

1. Resolve source → download zip → locate manifest (handle GitHub zipball nesting).
2. Validate manifest + version gate against DeviceKit version.
3. **Preview endpoint** (`POST /extensions/preview`) returns permissions + resolved
   sha256 *without installing* — powers the consent UI; the install pins that sha256 so
   installed bytes == previewed bytes. Checksum mismatch = hard failure.
4. Extract with **Zip-Slip defense** (reject absolute paths / `..` / escapes — port
   `_safe_extract_path()`), `backend/` → `backend/devicekit/extensions/<slug>/`.
5. Create `InstalledExtension` row (plan 01 table): slug, version, manifest JSON,
   config JSON (secrets excluded from serialization), status, source URL, sha256.
6. Hot-load: `importlib.import_module(f'devicekit.extensions.{slug}.{module}')`,
   register blueprint, register step types / FQL fields / AI tools, run
   `lifecycle.install`.
7. `requirements.txt` is **not** pip-installed unless `DEVICEKIT_ALLOW_EXTENSION_PIP=1`
   (pip runs arbitrary code at install time).

## Runtime tricks worth porting verbatim

- **Status guard (disable without restart):** Flask can't unregister a blueprint, so
  attach a `before_request` returning 503 when the extension's row status ≠ `active`
  (`_attach_status_guard()`, `plugin_service.py:969`). Disable also pauses its
  schedules and deregisters step types/FQL fields/AI tools (those registries are
  in-memory dicts, so removal is trivial — easier than ServerKit's problem).
- **Boot loader + self-heal:** on startup, load all active extensions; if extracted
  files are missing (image rebuild), re-install from `builtin-extensions/` or re-download
  from `source_url` (`repair_missing_plugins()`).
- **`ext_<slug>_*` table namespacing** with keep-vs-purge on uninstall
  (`extension_lifecycle.py`): uninstall keeps data by default, `?purge=true` drops
  exactly that prefix's tables.
- **Lifecycle hooks are convenience, not correctness:** failures logged and swallowed.

## The SDK seam (`devicekit_sdk`)

Port of `backend/app/plugins_sdk/__init__.py`: extensions import a stable façade, never
host internals. Exports: `db` session, `require_api_key`, `logger(slug)`,
`config(slug)`, `broadcast` (SSE), `devices` (read-only fleet accessors),
`device_control(slug, device_id)` (permission-gated adb/uia2 wrappers),
`register_step_type`, `register_fql_field`, `ai` (tool binder, plan 13), `jobs`
(plan 05), `notify` (plan 06), `devicekit_version()`.

The permission gate is declaration-based: `sdk.permissions.require(slug, "adb")` raises
unless the manifest declared it. Be as honest as ServerKit's ADR 0002: **this is not a
sandbox** — extensions run in-process with backend privileges. Safety comes from the
curated registry + consent card + pinned checksums. For device fleets that's an
acceptable v1 posture; out-of-process isolation is a documented future escalation.

## Registry: `devicekit-extensions` repo

Clone ServerKit's model (`serverkit-extensions`): a single curated `index.json`
(entries: slug, version, category, permissions, `source` release-zip URL, `sha256`,
logo), a JSON Schema, dependency-free Python validators (`validate.py`,
`verify_sources.py` — downloads every source and verifies checksums), and a CI workflow
that gates PRs. Backend fetches with an in-memory TTL cache and an offline fallback
chain: remote → last-good cache → bundled copy. Env var unset ⇒ public registry;
set-but-empty ⇒ disabled (air-gapped).

## Builtins & developer experience

- `builtin-extensions/<slug>/` at repo root; prove the platform by **extracting one
  existing feature** as the first builtin (ServerKit's "two-speed" decision D2 — e.g.
  visual regression: its step type, baselines table, routes, and view move to an
  extension while nothing else changes).
- Scaffolding CLI (port `scripts/new-extension.mjs`): `python scripts/new_extension.py
  <slug> [--backend] [--builtin]` plus `--validate <path>` running the same rules the
  installer enforces.
- `POST /extensions/install-local {path}` zips a working tree through the real
  pipeline for the dev loop.
- `docs/EXTENSIONS.md` author guide (ServerKit's is excellent — mirror its structure).

## API surface

`GET /extensions` · `POST /extensions/install|preview|install-local|install-upload` ·
`DELETE /extensions/<id>?purge=` · `POST /extensions/<id>/enable|disable` ·
`GET/PUT /extensions/<id>/config` · `GET /extensions/updates` · `POST /extensions/<id>/update` ·
`GET /extensions/manifest-spec` · `GET /extensions/contributions` (plan 04) ·
`GET /extensions/registry` (marketplace browse).

## Phases

1. ✅ Manifest spec + validator + `InstalledExtension` model + install pipeline + status
   guard + boot loader (no registry yet; local/URL installs only). — `extension_manifest.py`,
   `models/extension.py` (+ migration), `mixins/extensions.py`, `routes/extensions.py`;
   Flask-3 blueprint hot-load via a `_got_first_request` flag-flip; `test_extension_install.py`.
2. ✅ SDK + permission gate + step_type/FQL/AI-tool registration + lifecycle/tables. —
   `devicekit_sdk/` façade + `permissions.py`; STEP_TYPES became an execute-dispatch
   registry; FQL `_EXT_FQL_FIELDS` resolver; Prompture tools namespaced `<slug>__<name>`;
   `ext_<slug>_*` tables via `models` hook; `test_extension_contributions.py`.
3. ✅ Registry repo + fetch/cache + updates + consent preview flow. — sibling
   `devicekit-extensions` repo (index + schema + validators + CI); `extension_registry.py`
   (TTL cache + remote→cache→bundled fallback, `DEVICEKIT_REGISTRY_URL` semantics);
   `GET /extensions/registry|updates`, `POST /extensions/<id>/update`, registry-slug install;
   `test_extension_registry.py`.
4. ✅ First builtin + scaffolding CLI + author docs. — `builtin-extensions/devicekit-webhook-notify/`
   (step type + AI tool + blueprint + `ext_*` table + secret config + lifecycle);
   `scripts/new_extension.py` (`--backend`/`--builtin`/`--validate`, reusing the real
   validator); `docs/EXTENSIONS.md`; `test_builtin_extension.py`.

## Definition of done

A zip containing a manifest + a step type + a blueprint installs through the consent
flow, its step appears in the AutomationEditor with an auto-rendered config form, runs
in an automation, survives a backend restart, returns 503 when disabled, and uninstalls
cleanly (keep-data default, purge optional).
