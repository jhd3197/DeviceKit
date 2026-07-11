# Your First Extension in 10 Minutes

By the end of this you'll have scaffolded a real DeviceKit extension, installed it through the
production install pipeline, called its HTTP route, and seen its automation step type render a full
editor form **with zero frontend code**. Then you'll make it do something real.

You only need the **backend running** ([Getting Started](../getting-started.md)) — no device
required for the first pass. Run the commands from the **repo root**.

> The narrative behind every step is in the [Extension Guide](guide.md); the exhaustive field and
> SDK tables are the [Manifest Reference](manifest-reference.md) and
> [SDK Reference](sdk-reference.md). This tutorial is the fast path.

---

## 1. Scaffold it

The scaffolder (`backend/scripts/new_extension.py`) writes a manifest plus a `backend/` package
wired to the SDK, using the **same** `validate_manifest` rules the installer enforces:

```bash
python backend/scripts/new_extension.py hello-fleet --backend
```

It creates a throwaway working tree at `./hello-fleet/` and prints exactly what it wrote and how to
install it:

```
[ok] Scaffolded 'hello-fleet' at .../hello-fleet
     extension.json
     backend/__init__.py
     backend/routes.py
     backend/steps.py
     backend/lifecycle.py

Next: install it through the real pipeline (dev loop) —
     curl -X POST localhost:5050/extensions/install-local -d '{"path": ".../hello-fleet"}'
```

## 2. Tour what it wired

Four files, each mapping 1:1 onto a manifest reference.

**`extension.json`** — the manifest. Note the `module:attr` refs pointing into `backend/`:

```jsonc
{
  "name": "hello-fleet",
  "display_name": "Hello Fleet",
  "version": "0.1.0",
  "category": "utility",
  "permissions": [],
  "min_devicekit_version": "1.0.0",
  "entry_point": "routes:bp",                 // Flask blueprint in backend/routes.py
  "url_prefix": "/extensions/hello-fleet",
  "step_types": "steps:register",             // step type(s) in backend/steps.py
  "lifecycle": { "install": "lifecycle:on_install", "uninstall": "lifecycle:on_uninstall" }
}
```

**`backend/routes.py`** — a Flask blueprint mounted at `url_prefix`:

```python
from flask import Blueprint, jsonify

bp = Blueprint("hello_fleet", __name__)

@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "extension": "hello-fleet"})
```

**`backend/steps.py`** — an automation step type. `register()` returns
`{type_name: {label, category, config, execute}}`; `execute(client, config, device_id)` runs when
the step executes:

```python
def _execute(client, config, device_id):
    return "hello-fleet step ran"

def register():
    return {
        "hello_fleet.hello": {                 # dashes in the slug become underscores
            "label": "Hello Fleet Hello",
            "category": "Hello Fleet",
            "config": {"note": {"type": "text", "label": "Note", "required": False}},
            "execute": _execute,
        }
    }
```

**`backend/lifecycle.py`** — best-effort install/uninstall hooks using the SDK logger.

## 3. Validate before installing

Same rules as the installer, so you catch a malformed manifest before a failed install:

```bash
python backend/scripts/new_extension.py --validate hello-fleet
# [ok] hello-fleet v0.1.0 — manifest valid
```

## 4. Install through the real pipeline

Use the exact command the scaffolder printed (the `path` is the absolute scaffold dir):

```bash
curl -X POST localhost:5050/extensions/install-local \
  -H 'Content-Type: application/json' \
  -d '{"path": "/abs/path/to/hello-fleet"}'
```

`install-local` zips your working tree in memory (skipping `.git` / `node_modules` / `__pycache__`)
and pushes it through the **same** pipeline as a registry install: validate → persist the row →
Zip-Slip-safe extract → hot-load the blueprint and contributions. Confirm it landed:

```bash
curl localhost:5050/extensions
# {"extensions": [ { "name": "hello-fleet", "status": "active", ... } ], "count": ...}

curl localhost:5050/extensions/hello-fleet/ping
# {"ok": true, "extension": "hello-fleet"}
```

That second call proves your blueprint is live on the running app — no restart.

> **Tip:** install extensions with the backend in **non-debug** mode
> (`DEBUG_MODE=false python backend/app.py`). Flask's debug reloader can race the hot-load and leave
> a half-registered blueprint. In production `DEBUG_MODE` is already off.

## 5. See the step type — with zero frontend code

Open the dashboard (**http://localhost:5173**) → **Automations → New**. In the step palette you'll
find **Hello Fleet Hello** under the **Hello Fleet** category. Add it: DeviceKit renders its config
form — a single **Note** text field — straight from the `config` metadata in your `register()`.
**You wrote no frontend code.** That is the core payoff of a contributed step type.

Save the automation and **Run** it against any device; the step executes your `_execute` and returns
`"hello-fleet step ran"`.

## 6. Make it do something real

Edit `backend/steps.py` to actually act on the device, and declare the capability it needs. Say we
want the step to tap a coordinate from its config:

```python
import devicekit_sdk

def _execute(client, config, device_id):
    x = int(config.get("x", 540))
    y = int(config.get("y", 1200))
    devicekit_sdk.device_control("hello-fleet", device_id).tap(x, y)   # needs "device.control"
    return f"tapped ({x}, {y})"

def register():
    return {
        "hello_fleet.hello": {
            "label": "Hello Fleet Tap",
            "category": "Hello Fleet",
            "config": {
                "x": {"type": "number", "label": "X", "required": True},
                "y": {"type": "number", "label": "Y", "required": True},
            },
            "execute": _execute,
        }
    }
```

`device_control(...).tap` is **permission-gated** — add `device.control` to the manifest or it
raises `PermissionDenied`:

```jsonc
"permissions": ["device.control"],
```

Reinstall to pick up the changes (`install-local` force-reinstalls by default):

```bash
curl -X POST localhost:5050/extensions/install-local \
  -H 'Content-Type: application/json' -d '{"path": "/abs/path/to/hello-fleet"}'
```

Re-open the editor — the step now shows **X** and **Y** fields. Run it against a real device and it
taps.

## 7. Clean up / go further

Uninstall when you're done (add `?purge=1` to also drop any `ext_hello_fleet_*` tables):

```bash
curl -X DELETE localhost:5050/extensions/hello-fleet
rm -rf hello-fleet        # the throwaway working tree
```

Where to next:

- **More seams in one shot:** `python backend/scripts/new_extension.py rich-ext --full` scaffolds a
  device-scoped extension with `models`, `ai_tools`, `jobs` + `schedules`, an
  `automation_templates` file, and a `/ext/<slug>` blueprint.
- **Every contribution point explained:** the [Extension Guide](guide.md).
- **Look it up:** [Manifest Reference](manifest-reference.md) · [SDK Reference](sdk-reference.md).
- **Real examples:** the builtins in [`builtin-extensions/`](../../builtin-extensions) —
  `devicekit-browser` (step types + gated AI tools + a device pool),
  `devicekit-explorer` (a builtin frontend), `devicekit-notification-capture` (jobs + owned table +
  bus forwarding).
