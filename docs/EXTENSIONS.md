# Extension Author Guide

DeviceKit is a small core of device-fleet primitives plus optional **extensions**.
This document is the honest, single reference for building one: the manifest
schema, the contribution points, the backend SDK, the permission gate, lifecycle
hooks, install sources, the registry, and — importantly — the constraints you
will hit in production.

> If you only remember one thing: **a DeviceKit extension is backend-first.** Its
> real power is contributing *automation step types*, *fleet-query fields*, and
> *AI tools* that the existing core UI renders for you — a contributed step type
> gets the full AutomationEditor form **with zero frontend code**. Everything an
> extension declares runs in-process with the host's privileges, so safety comes
> from the curated registry, the consent card, and pinned checksums — not from a
> sandbox (see [Security posture](#security-posture--not-a-sandbox)).

The reference extension used throughout this guide is the first builtin,
`devicekit-webhook-notify` — it exercises **every** contribution seam (a step
type, an AI tool, a blueprint, a config schema with a secret, a data table, and
lifecycle hooks). Read it alongside this doc at
`builtin-extensions/devicekit-webhook-notify/`.

---

## Anatomy of an extension

An extension is a folder (zipped for distribution) with this layout:

```
devicekit-webhook-notify/
  extension.json        # manifest — the only required file (archive root)
  backend/              # a Python package hot-loaded into the running host
    __init__.py
    routes.py           # entry_point blueprint
    steps.py            # step_types contribution
    tools.py            # ai_tools contribution
    models.py           # models contribution (ext_<slug>_* tables)
    notify.py           # plain helper module
    lifecycle.py        # install/uninstall hooks
```

- The archive must carry `extension.json` at its **root**. GitHub zipball nesting
  (a `repo-sha/` prefix) is detected and stripped automatically.
- The `backend/` subtree is extracted to
  `devicekit/extensions/<slug_underscored>/` on the host (dashes in the slug
  become underscores so it is a valid Python package name — e.g.
  `devicekit-webhook-notify` → `devicekit/extensions/devicekit_webhook_notify/`).
  An `__init__.py` is created if the archive did not ship one, and the manifest is
  written into the package as `extension.json`.
- Modules are therefore imported as
  `devicekit.extensions.<slug_underscored>.<module>`. Inside the package, use
  relative imports (`from . import notify`) exactly as the builtin does.
- The `frontend/` half is reserved for a later plan; the current extractor ignores
  it. A DeviceKit extension delivers value through backend contribution points
  that plug into the **existing** core UI.

---

## The `extension.json` manifest

The authoritative, machine-readable contract is served at
`GET /extensions/manifest-spec` (from `extension_manifest.manifest_spec()`) and is
the same validator the installer and the scaffolding CLI's `--validate` run — so
they can never drift. Here is the full surface, annotated:

```jsonc
{
  // ---- required ----
  "name": "devicekit-webhook-notify",   // slug — regex ^[a-zA-Z0-9_-]+$
  "display_name": "Webhook Notifier",
  "version": "1.0.0",                    // loose semver: MAJOR.MINOR[.PATCH][-pre]

  // ---- metadata ----
  "category": "integration",             // automation | monitoring | integration | ai | utility
  "description": "…",
  "author": "Juan Denis",

  // ---- capability declarations (consent + SDK gate) ----
  "permissions": ["network"],            // subset of: adb, device.control, filesystem, network, llm

  // ---- version gate (enforced at install AND update) ----
  "min_devicekit_version": "1.0.0",      // optional
  "max_devicekit_version": "2.0.0",      // optional

  // ---- contribution points (all module:attr refs, all optional) ----
  "entry_point": "routes:bp",            // Flask blueprint, mounted at url_prefix
  "url_prefix": "/extensions/devicekit-webhook-notify",  // default /extensions/<slug>
  "models":     "models:register",       // owns ext_<slug>_* tables
  "step_types": "steps:register",        // automation step types
  "fql_fields": "fields:register",       // fleet-query fields
  "ai_tools":   "tools:register",        // Prompture AI tools

  "lifecycle": { "install": "lifecycle:on_install",
                 "uninstall": "lifecycle:on_uninstall" },

  // ---- settings form ----
  "config_schema": {
    "webhook_url":     { "type": "string", "label": "Webhook URL", "secret": true },
    "default_message": { "type": "string", "label": "Default message", "secret": false }
  }

  // ---- reserved / roadmap seams (validated if present) ----
  // "jobs":      [{ "kind": "…", "handler": "module:func" }],
  // "schedules": [{ "name": "…", "kind": "…", "interval_seconds": 60 }],
  // "automation_templates": ["templates/foo.json"],
  // "contributions": { "nav": [...], "routes": [...], "widgets": [...],
  //                    "command_palette": [...], "page_titles": {...} }
}
```

### Field rules (enforced by `validate_manifest`)

| Field | Rule |
|---|---|
| `name`, `display_name`, `version` | **Required.** Missing any is a hard failure. |
| `name` (slug) | Must match `^[a-zA-Z0-9_-]+$`. A bad slug is a hard failure. |
| `version` | Must match loose semver (e.g. `1.0.0`, `1.2`, `1.0.0-rc1`). |
| `category` | One of `automation`, `monitoring`, `integration`, `ai`, `utility`. Defaults to `utility`. |
| `permissions` | A list; each item must be a known permission (`adb`, `device.control`, `filesystem`, `network`, `llm`). |
| `entry_point`, `models`, `step_types`, `fql_fields`, `ai_tools` | Each must be a `module:attr` string matching `^[A-Za-z_][\w.]*:[A-Za-z_]\w*$`. |
| `lifecycle` | An object of `phase -> "module:func"`. |
| `url_prefix` | A string starting with `/`. Defaults to `/extensions/<slug>`. |
| `config_schema` | An object of `field -> spec`. |
| `min/max_devicekit_version` | Optional; the gate compares against the running DeviceKit `__version__` (currently `1.0.0`). |
| `contributions.*` | Known kinds (`nav`, `routes`, `widgets`, `command_palette`, `page_titles`) are shape-checked; **unknown kinds are tolerated** for forward-compatibility. |

Required-field and slug errors raise **immediately**; every other shape problem is
accumulated so you see all of them at once. The error message always points you
back to `GET /extensions/manifest-spec` or this doc.

The `module:attr` convention is used everywhere: `routes:bp` means "attribute `bp`
in module `routes`", resolved under `devicekit.extensions.<slug_underscored>.`.

---

## Contribution points — the differentiators

This is where a DeviceKit extension earns its keep. Each point is a `module:func`
reference in the manifest; the host imports it at activation and wires the result
into a core registry. All of the snippets below are from the webhook-notify
builtin.

### `step_types` — automation steps with free UI

`step_types` points at a zero-arg function returning
`{type_name: {label, category, config, execute}}`. The `execute` value is a
callable with the signature `execute(client, config, device_id) -> output`.

```python
# backend/steps.py
from . import notify


def _execute(client, config, device_id):
    message = config.get("message") or ""
    if not message:
        raise ValueError("message is required")
    url = config.get("webhook_url") or None
    record = notify.send(message, url=url)
    if record["error"]:
        raise Exception(f"Webhook delivery failed: {record['error']}")
    return f"Notified webhook (status {record['status_code']})"


def register():
    return {
        "notify.webhook": {
            "label": "Send Webhook Notification",
            "category": "Notify",
            "config": {
                "message":     {"type": "text", "label": "Message", "required": True},
                "webhook_url": {"type": "text", "label": "Webhook URL (optional override)",
                                "required": False},
            },
            "execute": _execute,
        }
    }
```

The payoff: **DeviceKit's AutomationEditor renders its config form directly from
the `config` metadata in the step registry.** Contributing a step type gets you a
fully-wired editor UI with **zero frontend code**. The host merges your entries
with the core `STEP_TYPES` (`step_type_registry()`), strips the `execute` callable
when serializing metadata to the editor (`get_step_types()`), and dispatches to
your `execute` when the step runs. `execute` must be callable or registration
raises. Registered step types are tracked per-slug and removed on disable/uninstall.

### `fql_fields` — make your data queryable via FQL

`fql_fields` points at a function returning `{field_name: {resolver, description}}`.
The `resolver` is a callable `resolver(device) -> value`; it becomes a queryable
field in DeviceKit's Fleet Query Language.

```python
# backend/fields.py
def _last_notified(device):
    # look up your ext_<slug>_* table, or compute from device state
    return device.get("last_notified_at", 0)


def register():
    return {
        "last_notified": {
            "resolver": _last_notified,
            "description": "Unix time of the last webhook notification for this device.",
        }
    }
```

Once registered, `last_notified` joins `SUPPORTED_FIELDS` and can be used in FQL
expressions like `last_notified < 1700000000`. The `resolver` must be callable or
registration raises. Fields are tracked per-slug and removed on disable/uninstall.

### `ai_tools` — extend the per-device AI assistant

`ai_tools` points at a function that **receives an AI binder** and registers tools
with the `@ai.tool` decorator. Each tool is bound into **every per-device Prompture
`ToolRegistry`**, namespaced `<slug_underscored>__<name>`.

```python
# backend/tools.py
from . import notify


def register(ai):
    @ai.tool
    def send_notification(message: str) -> str:
        """Send a notification message to the configured team webhook (Slack/Discord)."""
        record = notify.send(message)
        return (f"Sent (status {record['status_code']})"
                if not record["error"] else f"Failed: {record['error']}")
```

The tool's `__name__` becomes the tool name and its docstring becomes the tool
description, so this one binds as `devicekit_webhook_notify__send_notification`.
Obtain the binder via `devicekit_sdk.ai(slug)` (the host passes it to your
`register` for you).

### `entry_point` — a Flask blueprint

`entry_point` (`module:attr`) is a Flask `Blueprint`, mounted at `url_prefix`
(default `/extensions/<slug>`). It is imported from the extension package and
registered on the live app.

```python
# backend/routes.py
from flask import Blueprint, jsonify, request
from . import notify

bp = Blueprint("devicekit_webhook_notify", __name__)


@bp.route("/ping")
def ping():
    configured = bool(notify.resolve_webhook_url())
    return jsonify({"ok": True, "configured": configured})


@bp.route("/test", methods=["POST"])
def test_send():
    data = request.get_json(silent=True) or {}
    message = (data.get("message")
               or notify.devicekit_sdk.config(notify.SLUG).get("default_message")
               or "DeviceKit test notification")
    record = notify.send(message, url=data.get("webhook_url"))
    code = 200 if not record["error"] else 502
    return jsonify(record), code
```

The host attaches a **status guard** to every blueprint automatically — see
[The status guard](#the-status-guard--enabledisable). A blueprint failure at
activation is **fatal** (it flips the extension row to `error`); everything else is
best-effort.

### `models` — owned data tables (`ext_<slug>_*`)

`models` points at a function that **receives the SDK `db`** and defines the
extension's tables on the shared metadata. Table names **MUST** be prefixed
`ext_<slug>_` with dashes converted to underscores (the exact prefix is
`extension_manifest.table_prefix(slug)`), because that is the prefix the host
drops on `uninstall?purge`.

```python
# backend/models.py
from sqlalchemy import Table, Column, String, Float, Integer, Text

_TABLE_NAME = "ext_devicekit_webhook_notify_deliveries"
_table = None


def register(db):
    """Called at activation. Defines the deliveries table on the shared metadata (idempotent)."""
    global _table
    md = db.Base.metadata
    if _TABLE_NAME in md.tables:
        _table = md.tables[_TABLE_NAME]
    else:
        _table = Table(
            _TABLE_NAME, md,
            Column("id", String, primary_key=True),
            Column("text", Text),
            Column("status_code", Integer),
            Column("error", Text),
            Column("sent_at", Float),
        )
    return _table


def deliveries_table():
    if _table is None:
        raise RuntimeError("deliveries table not registered yet")
    return _table
```

The host calls your `register(db)`, then `db.create_all()`, so missing
`ext_<slug>_*` tables are created at install/activation. **Model registration is a
hard failure** (tables must exist); the other contribution points are best-effort.
Keep `register` idempotent — it runs at every activation (install, enable, and
boot), so guard against redefining a `Table` that is already on the metadata, as
shown above.

You can define tables with SQLAlchemy Core (`Table`, as above) or declaratively on
`db.Base`. Read/write rows through a short-lived session:

```python
from .models import deliveries_table
import devicekit_sdk

with devicekit_sdk.db.session() as s:
    s.execute(deliveries_table().insert().values(**record))
```

---

## The backend SDK (`devicekit_sdk`)

Depend on the SDK, not on host internals. The host wires itself into the SDK at
boot (`set_host`), and every façade call routes to the live `Client`. Import only
from `devicekit_sdk`; never reach into `devicekit.*`.

```python
import devicekit_sdk
from devicekit_sdk import db, logger, config, broadcast, devices, device_control, \
    register_step_type, register_fql_field, ai, require_permission, PermissionDenied
```

| Export | What it is | Usage |
|---|---|---|
| `db` | Persistence seam. `db.Base` (shared metadata), `db.session()` (short-lived transactional session ctx-mgr), `db.engine`, `db.create_all()`. | `with db.session() as s: s.execute(...)` |
| `logger(name)` | Namespaced logger `devicekit.ext.<name>`. | `log = logger("my-ext")` |
| `config(slug)` | The extension's saved config **including secrets** — the in-process view (the API response masks secrets; this does not). Read-only dict. | `config("my-ext").get("api_key")` |
| `broadcast(event_type, data)` | Push an SSE event to all connected clients. | `broadcast("extension_event", {...})` |
| `devices` | Read-only fleet accessors: `devices.list()`, `devices.get(device_id)`. | `for d in devices.list(): ...` |
| `device_control(slug, device_id)` | Permission-gated device control object. | see below |
| `register_step_type(name, spec)` | Register an automation step type (also tracked for teardown). | usually via `step_types` contribution |
| `register_fql_field(name, spec)` | Register a fleet-query field (also tracked for teardown). | usually via `fql_fields` contribution |
| `ai(slug)` | Returns the AI binder for `ai_tools` registration. | `ai("my-ext").tool(fn)` |
| `require_permission(slug, cap)` | The capability gate — raises `PermissionDenied` unless `cap` is declared in the manifest `permissions`. | `require_permission("my-ext", "network")` |
| `permissions` | The gate module (`has`, `require`, `declared_permissions`, `unknown_permissions`). | `permissions.has(slug, "adb")` |
| `PermissionDenied` | Exception raised by the gate. | `except PermissionDenied: ...` |
| `devicekit_version()` | The running DeviceKit version string (for in-extension compat checks). | `if devicekit_version() >= "1.1": ...` |
| `jobs`, `notify` | Roadmap seams (plans 05/06). Importable today so you can code against a stable name, but **any attribute access raises `NotImplementedError`** until those platforms land. | — |

### `device_control` — the gated device surface

`device_control(slug, device_id)` returns an object whose methods route to the
host and are **permission-gated**:

```python
dc = devicekit_sdk.device_control("my-ext", device_id)
dc.tap(x, y)          # requires "device.control"
dc.press(key)         # requires "device.control"
dc.screenshot()       # requires "device.control"
dc.shell("pm list packages")  # requires "adb" (raw shell)
```

`tap`/`press`/`screenshot` require the `device.control` permission; `shell` (raw
adb shell) requires `adb`. Undeclared use raises `PermissionDenied`.

Errors from a blueprint follow the house convention:
`return jsonify({'error': 'message'}), status`.

---

## Permissions & the gate

`permissions` in the manifest is both a **consent step** at install and an
**enforced gate** at call time. The known capabilities are:

| Permission | Grants |
|---|---|
| `adb` | Raw adb shell (`device_control(...).shell(...)`). |
| `device.control` | Tap / press / screenshot on a device. |
| `filesystem` | Host filesystem access. |
| `network` | Outbound network (e.g. the webhook POST). |
| `llm` | LLM / AI calls. |

The gate is **declaration-based**: `require_permission(slug, cap)` looks up the
installed row's declared permissions and raises `PermissionDenied` unless `cap` is
present. The webhook helper gates its send:

```python
from devicekit_sdk import require_permission

def send(text, url=None):
    require_permission("devicekit-webhook-notify", "network")  # declared in the manifest
    ...
```

**Be honest: this is NOT a sandbox.** Extensions run in-process with the host's
full privileges. The gate is an honest guardrail against *accidental undeclared*
use — nothing stops determined code from calling host internals directly. Real
safety comes from three other things: the **curated registry**, the **consent
card** the user approves (which shows exactly the permissions you declared), and
the **pinned sha256** that guarantees installed bytes equal previewed bytes.
Under-declaring or over-declaring both read badly at the consent step. Permissions
the host does not recognize surface as an "unknown" badge on the consent card
(`permissions.unknown_permissions`).

---

## Lifecycle hooks

Declared under `lifecycle` as `phase -> "module:func"`, resolved under the
extension package. Hooks are **best-effort — failures are logged and swallowed**;
they are convenience, not correctness.

```python
# backend/lifecycle.py
import devicekit_sdk

SLUG = "devicekit-webhook-notify"
log = devicekit_sdk.logger(SLUG)


def on_install(client):
    log.info("Webhook Notifier installed. Set 'webhook_url' in the extension config to enable delivery.")


def on_uninstall(client, purge=False):
    log.info(f"Webhook Notifier uninstalled (purge={purge}).")
```

- `install` runs **after** files are extracted and the blueprint/contributions are
  wired (at install time only, not at every boot).
- `uninstall` runs **before** files are removed and receives a `purge` kwarg
  indicating whether the caller asked to drop the extension's data.
- The host forwards only the kwargs your hook actually declares (via signature
  inspection), so `on_install(client)` and `on_uninstall(client, purge=...)` both
  work — the first positional arg is always the DeviceKit `Client`.

---

## Config (`config_schema`)

Declare a `config_schema` and the settings are stored per-extension and exposed
through the API. Each field is `{type, label, secret?, ...}`:

```jsonc
"config_schema": {
  "webhook_url":     { "type": "string", "label": "Webhook URL", "secret": true },
  "default_message": { "type": "string", "label": "Default message", "secret": false }
}
```

- Read config in your backend with `devicekit_sdk.config(slug)` — this is the
  **in-process view that includes secret values**, which is what a running
  extension needs.
- Fields marked `"secret": true` are **masked in every API response** (`GET
  /extensions/<slug>`, `GET /extensions/<slug>/config`) — the value serializes as
  `••••••`. The raw secret never leaves the process via the API; it is only
  available in-process through `devicekit_sdk.config()`.
- Update config with `PUT /extensions/<slug>/config` (a JSON object of
  `field -> value`, merged into the stored config).

```python
webhook_url = devicekit_sdk.config("devicekit-webhook-notify").get("webhook_url", "")
```

---

## The status guard & enable/disable

Every extension blueprint gets an automatic `before_request` **status guard**.
The in-DB `status` is authoritative:

- `active` → routes serve normally.
- `disabled` / `error` / uninstalled → routes return **503** with
  `{"error": "...", "status": "..."}`.

This means disabling an extension **actually stops serving it without a restart**,
even though Flask cannot unregister a blueprint from a running app. Reinstall in a
running process gets a fresh unique blueprint name (`ext_<slug>_<seq>`) so it never
collides with a same-named blueprint Flask still holds.

- **`POST /extensions/<slug>/disable`** sets status `disabled`, deregisters the
  in-memory contribution points (step types, FQL fields, AI tools — plain dicts,
  removed instantly), and leaves the blueprint mounted but serving 503.
- **`POST /extensions/<slug>/enable`** sets status `active` and **re-registers**
  the contribution points (the blueprint was never removed, so it just starts
  passing the guard again).

### Boot loader + self-heal

At boot, `load_all_extensions(app)` runs after core blueprints register (the app
is not yet serving, so registration is normal):

1. **Self-heal (`repair_missing_extensions`)** — for any installed row whose
   extracted package is missing (e.g. after an image rebuild), it re-installs from
   `builtin-extensions/` (source `builtin`) or re-downloads from `source_url`
   (source `url`/`registry`). If there is no re-install source, the row is flagged
   `error` with "re-upload" guidance.
2. **Hot-load** — every `active`/`disabled` extension is re-activated from its
   stored manifest (contributions re-registered, blueprint re-mounted). A failure
   flips that row to `error` with the message, without taking down the rest.

Because the installed **row** (with the full verbatim manifest and pinned sha256)
is the source of truth, the platform survives restarts without re-reading extracted
files.

---

## Install sources & the API surface

All sources funnel through one pipeline (`_install_from_buffer`) so behavior is
identical: read manifest → `validate_manifest` → `assert_devicekit_compatible` →
persist the row (status `active`) → extract with Zip-Slip defense → hot-load. If
hot-load fails, the row flips to `error` and the error is surfaced.

### The full route list (`routes/extensions.py`)

| Method & path | Purpose |
|---|---|
| `GET /extensions` | List installed extensions (`{extensions, count}`). |
| `GET /extensions/manifest-spec` | The machine-readable manifest contract. |
| `GET /extensions/registry` | Browse the registry, enriched with local install state. `?refresh=1` forces a re-fetch. |
| `GET /extensions/updates` | Installed versions that have a newer registry version. |
| `POST /extensions/preview` | Consent preview — resolve a `url`/`path` to manifest + pinned `sha256` without installing. |
| `POST /extensions/install` | Install by `slug` (registry), `url`, or `path`; accepts `sha256`, `force`. |
| `POST /extensions/install-local` | Zip a working tree on the host by `path` and install it (dev loop; `force` defaults true). |
| `POST /extensions/install-upload` | Install an uploaded zip (multipart field `file`). |
| `GET /extensions/<slug>` | Get one extension (config secrets masked). |
| `DELETE /extensions/<slug>` | Uninstall. `?purge=1` also drops `ext_<slug>_*` tables. |
| `POST /extensions/<slug>/update` | Reinstall at the registry's current (pinned) version. |
| `POST /extensions/<slug>/enable` | Enable (status `active`). |
| `POST /extensions/<slug>/disable` | Disable (status `disabled`, 503 without restart). |
| `GET /extensions/<slug>/config` | Read config (secrets masked). |
| `PUT /extensions/<slug>/config` | Merge a JSON object into the stored config. |

### The preview / consent flow (sha256 pinning)

`POST /extensions/preview` with `{"url": ...}` or `{"path": ...}` resolves and
downloads the source, reads the manifest, validates it, and returns a consent card:

```jsonc
{
  "slug": "devicekit-webhook-notify",
  "display_name": "Webhook Notifier",
  "version": "1.0.0",
  "category": "integration",
  "description": "…",
  "permissions": ["network"],          // exactly what the user consents to
  "contributions": { … },
  "config_schema": { … },
  "source_url": "https://…",
  "sha256": "…",                        // pin the install to these bytes
  "warnings": [ "…already installed…", "…version-gate mismatch…" ]
}
```

Pass the returned `sha256` back to `POST /extensions/install` (`{"url": ...,
"sha256": ...}`) and the installer **hard-fails on any mismatch** (case-insensitive,
before extraction) — so what installs is byte-identical to what was previewed and
consented to.

### Install source summary

| Source | How | Endpoint |
|---|---|---|
| Registry slug | Curated index; bundled entries come from `builtin-extensions/`, others download from the entry's pinned `source` + `sha256`. | `POST /extensions/install` with `{"slug": ...}` |
| URL (GitHub / release / zip) | Paste a URL; optionally pin `sha256`. GitHub zipball nesting handled. | `POST /extensions/install` with `{"url": ...}` |
| Uploaded zip | Multipart upload. | `POST /extensions/install-upload` |
| Local path (dev) | Host path zipped in memory (dev junk like `.git`/`node_modules`/`__pycache__` skipped) and pushed through the same pipeline. | `POST /extensions/install-local` with `{"path": ...}` |
| Builtin | In-repo `builtin-extensions/<slug>` installed via the registry entry's `bundled` flag. | `install_builtin_extension(slug)` (via registry install) |

Zip-Slip is rejected on every entry (absolute paths, drive letters, `..`, and any
entry escaping the destination). A `requirements.txt` inside an extension is **not**
pip-installed unless the operator opts in — see [Security posture](#security-posture--not-a-sandbox).

### Uninstall: keep vs purge

`DELETE /extensions/<slug>` defaults to **keep-data**: it runs the `uninstall`
hook, deregisters contributions, removes the extracted files, and deletes the
installed row — but **leaves `ext_<slug>_*` tables intact**. Add `?purge=1` to also
drop exactly those tables (the `purge=True` value is forwarded to your `uninstall`
hook first).

### Updates

`GET /extensions/updates` compares installed versions to the registry.
`POST /extensions/<slug>/update` reinstalls at the registry's current version
(force reinstall, pinned to the registry entry's checksum). The version gate is
re-checked on update, not just at first install.

---

## The registry (`devicekit-extensions`)

The curated index lives in the `devicekit-extensions` repo as an `index.json`.
`extension_registry.py` fetches it with an in-memory TTL cache
(`DEVICEKIT_REGISTRY_TTL`, default 3600s) and an offline fallback chain:
**remote → last-good cache → bundled copy**. A refresh **never raises** — a network
failure keeps serving the last good data — and `source_label()` reports where the
current data came from (`remote` / `cache` / `bundled`).

`DEVICEKIT_REGISTRY_URL` semantics (matching ServerKit):

| Value | Behavior |
|---|---|
| **unset** | The public registry (`https://raw.githubusercontent.com/jhd3197/devicekit-extensions/main/index.json`). |
| **set but empty** | Disabled / air-gapped — the bundled copy only (also how tests stay offline). |
| **set to a URL** | That URL. |

Each registry entry surfaces a fixed field set: `slug`, `display_name`,
`description`, `version`, `category`, `author`, `first_party`, `bundled`,
`permissions`, `min/max_devicekit_version`, `source`, `sha256`, `repo`, `homepage`,
`logo`, `screenshots` (anything else is stripped). Entries flagged `bundled` install
from `builtin-extensions/`; the rest download from the entry's pinned `source` and
are verified against its `sha256`.

---

## Scaffolding CLI

`backend/scripts/new_extension.py` scaffolds and validates extensions using the
**same** `validate_manifest` rules the installer enforces (so the CLI and pipeline
never drift):

```bash
# Scaffold a manifest-only extension in the current directory
python scripts/new_extension.py my-extension

# Scaffold with a backend/ package wired to the SDK (blueprint + step type + lifecycle)
python scripts/new_extension.py my-extension --backend

# Scaffold under builtin-extensions/ (for an in-repo builtin)
python scripts/new_extension.py my-extension --builtin --backend

# Validate an existing extension (dir or extension.json) — same rules as install
python scripts/new_extension.py --validate builtin-extensions/devicekit-webhook-notify
```

- The slug is checked against `SLUG_RE` before anything is written; the CLI refuses
  to overwrite an existing directory.
- `--backend` writes `backend/__init__.py`, `routes.py` (a `/ping` blueprint),
  `steps.py` (a sample step type), and `lifecycle.py`, plus a manifest wiring them
  up (`entry_point`, `step_types`, `lifecycle`).
- The CLI prints the exact `curl` to install what it scaffolded —
  `install-local` for a working-tree extension, or the bundled `install` for a
  `--builtin` one.
- `--validate` exits non-zero and prints the validation error on failure — use it
  in CI to catch malformed manifests before a failed install.

---

## Recipe: convert a core feature into a builtin extension

The webhook notifier is the worked example: a self-contained feature (post to a
webhook) that lives entirely in an extension while plugging into core surfaces.
The general recipe:

1. `python scripts/new_extension.py <slug> --builtin --backend` to scaffold under
   `builtin-extensions/<slug>/`.
2. Move the feature's logic into a plain helper module (like `notify.py`) that
   imports only from `devicekit_sdk`.
3. Expose it through the contribution points that fit:
   - an **automation step type** (`steps.py`) so users can drop it into automations
     with a free editor form;
   - an **AI tool** (`tools.py`) so the assistant can invoke it per-device;
   - a **blueprint** (`routes.py`) for a health/test HTTP surface;
   - a **`models.py`** owning an `ext_<slug>_*` table if it needs to persist data;
   - **lifecycle hooks** for install/uninstall messaging or seeding.
4. Declare `config_schema` for any settings (mark secrets `secret: true`), and
   declare the minimal `permissions` the feature actually uses.
5. Validate: `python scripts/new_extension.py --validate builtin-extensions/<slug>`.
6. Install through the real pipeline:
   `curl -X POST localhost:5050/extensions/install-local -d '{"path": ".../builtin-extensions/<slug>"}'`.

### The webhook-notify walkthrough

Trace how the pieces connect in `devicekit-webhook-notify`:

- **`notify.py`** is the single source of behavior: `send(text, url=None)` gates on
  `network`, resolves the webhook URL from config, POSTs a `{"text": ...}` payload,
  records the delivery into `ext_devicekit_webhook_notify_deliveries`, and
  broadcasts an `extension_event` SSE. Delivery failures are recorded, not raised.
- **`steps.py`** wraps `notify.send` as the `notify.webhook` step type — its `config`
  metadata (a required `message`, an optional `webhook_url`) becomes the
  AutomationEditor form automatically.
- **`tools.py`** wraps `notify.send` as `send_notification`, bound into every
  per-device Prompture registry as
  `devicekit_webhook_notify__send_notification`.
- **`routes.py`** exposes `/ping` (is a URL configured?) and `POST /test`
  (send a one-off), both status-guarded.
- **`models.py`** defines the deliveries table on the shared metadata, created at
  install and dropped only on `uninstall?purge`.
- **`lifecycle.py`** logs install/uninstall messages (best-effort).
- **`extension.json`** declares just `network`, wires all five refs, and defines a
  two-field `config_schema` with the webhook URL marked `secret`.

One helper, five seams, and the whole thing plugs into automations, the AI
assistant, FQL-adjacent data, and an HTTP surface — with no frontend code.

---

## Security posture / not-a-sandbox

Be clear-eyed about the trust model:

- **Extensions run in-process** with the host's full privileges. The permission
  gate is *declaration-based* enforcement, not isolation — it prevents accidental
  undeclared capability use, nothing more.
- Safety is layered from things that *do* hold: a **curated registry**, a
  **consent card** the user approves (showing exactly the declared `permissions`),
  and a **pinned sha256** that guarantees installed bytes equal previewed bytes.
- **Zip-Slip is rejected** on every archive entry (absolute paths, drive letters,
  `..`, destination escapes).
- **Pip is gated.** An extension may ship `requirements.txt`, but the host will
  **not** run pip unless the operator sets `DEVICEKIT_ALLOW_EXTENSION_PIP` to
  `1`/`true`/`yes` — because pip runs arbitrary code at install time with the
  backend's privileges. Otherwise the installer logs the skipped requirements and
  tells the operator to review and install them manually if trusted.

If you need a hard security boundary, an extension is not it — treat installing one
with the same caution as running any third-party code on the host.
