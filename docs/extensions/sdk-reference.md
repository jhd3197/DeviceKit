# SDK Reference — `devicekit_sdk`

A lookup table for the stable façade an extension backend imports. Depend on **`devicekit_sdk`**,
never on `devicekit.*` internals — the host wires itself into the SDK at boot (`set_host`) and
every call routes to the live `Client`. Internal `devicekit.*` restructures don't break extensions;
only this surface is contract.

For the narrative — how these fit into contribution points, lifecycle, and the permission model —
read the [Extension Guide](guide.md). For the manifest fields, the
[Manifest Reference](manifest-reference.md).

```python
import devicekit_sdk
from devicekit_sdk import (
    db, logger, config, broadcast, devices, device_control,
    register_step_type, register_fql_field, ai, jobs, notify,
    extension, provides, ExtensionUnavailable,
    require_permission, permissions, PermissionDenied, devicekit_version,
)
```

**Versioning.** `devicekit_version()` returns the platform version (`"1.0.0"`). The *SDK contract*
version is a separate constant `SDK_VERSION = "1.0.0"` in
`backend/devicekit/mixins/extensions.py` (not in `devicekit_sdk`), served at
`GET /extensions/sdk-version` and mirrored by the frontend `devicekit-sdk` alias — a test asserts
the two agree.

---

## Top-level exports

`__all__` is the authoritative public list (`backend/devicekit_sdk/__init__.py`):

| Export | Signature | What it does |
| --- | --- | --- |
| `devicekit_version` | `devicekit_version() -> str` | The running DeviceKit version (`"1.0.0"`). Use for in-extension compat checks. |
| `db` | *(singleton)* | Persistence seam — see [db](#db). |
| `logger` | `logger(name) -> logging.Logger` | A namespaced logger `devicekit.ext.<name>`. Convention: pass your slug. |
| `config` | `config(slug) -> dict` | The extension's saved config **including secret values** — the in-process view (the API response masks secrets; this does not). `{}` before boot. Read-only. |
| `broadcast` | `broadcast(event_type, data) -> None` | Push an SSE event to every connected client. No-op before boot. |
| `devices` | *(singleton)* | Read-only fleet accessors — see [devices](#devices). |
| `device_control` | `device_control(slug, device_id) -> _DeviceControl` | Permission-gated device control — see [device_control](#device_control). |
| `register_step_type` | `register_step_type(type_name, spec) -> None` | Register an automation step type (tracked for teardown). Usually via the `step_types` contribution. |
| `register_fql_field` | `register_fql_field(name, spec) -> None` | Register a fleet-query field (tracked for teardown). Usually via the `fql_fields` contribution. |
| `ai` | `ai(slug) -> _AiBinder` | The AI-tool binder — see [ai](#ai). |
| `extension` | `extension(slug) -> _ExtensionClient` | A client for a **sibling** extension's provided surface — see [sibling extensions](#sibling-extensions-plan-17). |
| `provides` | `provides(slug) -> _ProvidesBinder` | The binder for your own sibling-callable surface — see [sibling extensions](#sibling-extensions-plan-17). |
| `ExtensionUnavailable` | `class ExtensionUnavailable(RuntimeError)` | Raised by an `extension(slug)` call when the sibling is not installed or not active. |
| `jobs` | *(singleton)* | Background-work seam — see [jobs](#jobs). |
| `notify` | *(singleton)* | Notification-bus seam — see [notify](#notify). |
| `appdriver` | *(module)* | App-driver framework: provision + version adapters + policy — see [appdriver](#appdriver-app-driver-framework-plan-18). |
| `require_permission` | `require_permission(slug, capability) -> True` | Alias of `permissions.require`. Raises `PermissionDenied` unless declared. |
| `permissions` | *(module)* | The permission gate — see [permissions](#permissions). |
| `PermissionDenied` | `class PermissionDenied(PermissionError)` | Raised when an extension uses an undeclared capability. |
| `set_host` / `get_host` | `set_host(client)` / `get_host()` | Boot wiring — the host calls `set_host` once; extensions rarely need `get_host`. |

---

## `db`

The persistence seam. Extensions declare tables on the shared metadata and use short-lived
sessions. Table names **must** be prefixed `ext_<slug>_` (dashes → underscores).

| Member | Signature | What it does |
| --- | --- | --- |
| `db.Base` | property → declarative `Base` | The shared SQLAlchemy metadata. Define tables on `db.Base.metadata` (Core `Table`) or on `db.Base` (declarative). |
| `db.session` | `db.session()` → context manager | A short-lived transactional session: commit on success, rollback on exception, always closed. |
| `db.engine` | property → `Engine` | The shared SQLAlchemy engine. |
| `db.create_all` | `db.create_all() -> None` | Create every table registered on the shared metadata (the host also calls this at activation). |

```python
from .models import deliveries_table
import devicekit_sdk

with devicekit_sdk.db.session() as s:
    s.execute(deliveries_table().insert().values(**record))
```

---

## `devices`

Read-only fleet accessors. For *acting* on a device, use [`device_control`](#device_control).

| Member | Signature | What it does |
| --- | --- | --- |
| `devices.list` | `devices.list() -> list[dict]` | All devices in the merged fleet. `[]` before boot. |
| `devices.get` | `devices.get(device_id) -> dict | None` | One device dict, or `None` on miss/error. |

---

## `device_control`

`device_control(slug, device_id)` returns an object whose methods route to the host and are
**permission-gated** — an undeclared capability raises `PermissionDenied`. The `slug` is yours, so
the gate checks *your* declared permissions.

| Method | Signature | Requires |
| --- | --- | --- |
| `tap` | `tap(x, y)` | `device.control` |
| `press` | `press(key)` | `device.control` |
| `screenshot` | `screenshot()` | `device.control` |
| `shell` | `shell(command)` — runs `adb shell <command>` | `adb` |
| `forward` | `forward(local_port, remote="localabstract:chrome_devtools_remote")` — `adb forward tcp:<local_port> → <remote>` (default the Chrome DevTools socket), returns adb stdout | `adb` |
| `remove_forward` | `remove_forward(local_port)` — tears down the forward | `adb` |
| `install_apk` | `install_apk(apk_path) -> (ok, output)` — `adb install -r` a local APK (the app-driver provisioning primitive) | `adb` |
| `uninstall_app` | `uninstall_app(package)` — `adb uninstall` (used by the gated reprovision) | `adb` |
| `app_version` | `app_version(package) -> str | None` — installed `versionName` via `dumpsys package`, `None` if absent (the cheap per-call read the version-adapter resolver uses) | `device.control` |

```python
dc = devicekit_sdk.device_control("my-ext", device_id)
dc.tap(540, 1200)                      # needs "device.control"
port = dc.forward(9300)                # needs "adb" — how devicekit-browser reaches Chrome CDP
dc.shell("pm list packages")           # needs "adb"
dc.remove_forward(9300)
```

---

## `ai`

`ai(slug)` returns a binder passed to your `ai_tools` register function. Each tool is bound
(namespaced `<slug>__<name>`) into **every** per-device Prompture `ToolRegistry`.

| Member | Signature | What it does |
| --- | --- | --- |
| `ai(slug).tool` | `tool(func=None, *, is_write=True)` | Decorator registering an AI tool. Bare `@ai.tool` (defaults `is_write=True`) or `@ai.tool(is_write=False)` for a read-only tool. The function `__name__` is the tool name; its docstring is the description. |

**Gating is not optional for extensions.** `is_write=True` tools are **always** routed through the
host confirmation gate — even in autonomous mode — because third-party code never gets unattended
hardware access ([ADR 0005](../adr/0005-extension-ai-tools-always-gated.md)). Read tools
(`is_write=False`) run free. In `observe` mode write tools are hidden entirely. See
[AI Agent](../ai-agent.md#the-confirmation-gate) for the gate.

```python
def register(ai):
    @ai.tool                       # write tool → always gated
    def send_notification(message: str) -> str:
        """Send a message to the configured team webhook."""
        ...

    @ai.tool(is_write=False)       # read tool → runs free
    def last_status() -> str:
        """Return the last delivery status."""
        ...
```

---

## Sibling extensions (plan 17)

One extension can depend on and call another instead of reimplementing it. Declare the dependency
with the `requires_extensions` manifest key (enforced at install); expose a surface with the
`provides` key; call it with `extension(slug)`.

| Member | Signature | What it does |
| --- | --- | --- |
| `extension` | `extension(slug) -> _ExtensionClient` | A thin client for a sibling's provided surface. |
| `_ExtensionClient.<method>` | `<method>(*args, **kwargs)` | Dispatches **in-process** to the sibling's registered method. Raises `ExtensionUnavailable` if the sibling isn't installed/active, `AttributeError` if it provides no such method. Resolved fresh per call, so a runtime disable is caught. |
| `_ExtensionClient.available` | `available() -> bool` | `True` if the sibling is installed and active *right now* — a cheap pre-check to branch without catching the exception. |
| `provides` | `provides(slug) -> _ProvidesBinder` | The binder passed to your `provides` register function. |
| `provides(slug).method` | `method(func=None, *, name=None)` | Register a callable siblings may invoke. Bare (`api.method(fetch)`) or named (`api.method(fetch, name="get")`). |

Calls dispatch in-process (no HTTP hop, no serialization) but through a lookup that **honours the
status guard** — a disabled or errored provider raises `ExtensionUnavailable`, so a dependent
degrades cleanly instead of hitting a mystery `503` mid-flow. It is *not* a raw import of the
sibling's module: internals stay private.

```python
# provider (devicekit-browser/backend/api.py)
def fetch(pool="default", url=None, fmt="html"):
    ...
    return {"device_id": device_id, "url": url, fmt: body}

def register(api):                     # manifest: "provides": "api:register"
    api.method(fetch)
```

```python
# consumer (devicekit-serp)  —  manifest: "requires_extensions": {"devicekit-browser": ">=0.1.0"}
import devicekit_sdk

browser = devicekit_sdk.extension("devicekit-browser")
if not browser.available():
    raise devicekit_sdk.ExtensionUnavailable("devicekit-browser is disabled")
result = browser.fetch(pool="default", url="https://www.google.com/search?q=cats")
html, served_by = result["html"], result["device_id"]
```

**Lifecycle.** Install refuses when a required sibling is absent/incompatible; uninstalling a
depended-on extension is **blocked** while an active dependent needs it (force to override);
disabling one only warns and lets dependents degrade. See the
[Manifest Reference](manifest-reference.md#extension-dependencies).

---

## `jobs`

The background-work seam (plan 05). Handlers and schedules registered during activation are tracked
against your slug, so disable pauses them and uninstall deletes them.

| Member | Signature | What it does |
| --- | --- | --- |
| `jobs.enqueue` | `enqueue(kind, payload=None, max_attempts=3, priority=0, delay_ms=0, owner_type=None, owner_id=None)` | Enqueue durable background work. |
| `jobs.register` | `register(kind, handler, replace=True)` | Map `kind → handler(job_dict) -> result` (tracked for teardown). Usually via the `jobs` manifest key. |
| `jobs.schedule` | `schedule(name, kind, interval_seconds=None, cron=None, payload=None, max_attempts=1, startup_delay_seconds=0)` | Idempotently declare a periodic schedule owned by your extension. Usually via the `schedules` manifest key. |
| `jobs.get` | `get(job_id) -> dict` | Fetch one job. |
| `jobs.list` | `list(**kwargs) -> list[dict]` | List jobs. |

> The scheduler tick is ~15s, so effective cadence floors around 15–30s. For low-latency waits
> (e.g. OTP), poll the source directly inside a step/tool rather than via a schedule.

---

## `notify`

The notification-bus seam (plan 06). Emit fleet events through the host's unified bus; register your
own catalog entries. In-app delivery (SSE) is immediate; webhook/email ride the queue when
configured.

| Member | Signature | What it does |
| --- | --- | --- |
| `notify.send` | `send(event_key, data=None, recipient="default", subject_type=None, subject_id=None, severity=None)` | Emit a notification event — persists + delivers. |
| `notify.register_event` | `register_event(event_key, title, severity="info", category="general", body="", deep_link="")` | Register a catalog entry so `send` renders it (tracked for teardown). |

```python
devicekit_sdk.notify.register_event("myext.captured", "{package}: {title}",
                                    severity="info", category="monitoring")
devicekit_sdk.notify.send("myext.captured", data={...}, subject_type="device",
                          subject_id=device_id)
```

---

## `permissions`

The declaration-based gate. It is **not a sandbox** — extensions run in-process with the host's
privileges ([ADR 0001](../adr/0001-in-process-extensions.md)). The gate makes privileged capability
use *declared*: raise unless the manifest lists it.

| Member | Signature | What it does |
| --- | --- | --- |
| `permissions.declared_permissions` | `declared_permissions(slug) -> set[str]` | The permissions the installed extension declared. Empty if not installed / before boot. |
| `permissions.has` | `has(slug, capability) -> bool` | `True` if `capability` is declared. |
| `permissions.require` | `require(slug, capability) -> True` | Raise `PermissionDenied` unless declared. (Also exported as `require_permission`.) |
| `permissions.unknown_permissions` | `unknown_permissions(permissions) -> list[str]` | Entries not in `KNOWN_PERMISSIONS` — powers the consent UI's "unknown" badge. |
| `permissions.KNOWN_PERMISSIONS` | `set` | `{"adb", "device.control", "filesystem", "network", "llm"}`. |

```python
from devicekit_sdk import require_permission

def send(text, url=None):
    require_permission("devicekit-webhook-notify", "network")  # declared in the manifest
    ...
```

The five capabilities and what each grants are documented in the
[Manifest Reference](manifest-reference.md#permissions) and the
[Guide's permission section](guide.md#permissions--the-gate).

---

## `appdriver` (app-driver framework, plan 18)

`devicekit_sdk.appdriver` is the reusable core for extensions that **provision and drive a
third-party app** across version drift. Pair it with a `device_requirements` manifest key. The
worked consumer is `devicekit-vpn`.

**Provisioning** — install a user-supplied, hash-pinned APK and record the result in the
extension-owned `ext_<slug>_provisioned` table:

| Member | Signature | What it does |
| --- | --- | --- |
| `provision` | `provision(slug, device_id, *, package, apk_b64=None, apk_bytes=None, expected_sha256=None, expected_version=None, serial="") -> dict` | Verify the pinned sha256, `adb install -r`, read back `versionName`, record (`ok` / `version_mismatch` / `install_failed`). Raises `ProvisionError` on a checksum mismatch or failed install. |
| `reprovision` | `reprovision(slug, device_id, *, package, ...)` | Destructive: uninstall then `provision` the pin (a downgrade Play won't do). Gate it in your extension. |
| `installed_version` | `installed_version(slug, device_id, package) -> str | None` | The device's installed `versionName` (permission-gated read). |
| `provisioned_table` / `record_provision` / `get_provision` / `list_provisions` | | Define/query the `ext_<slug>_provisioned` ledger (namespaced, dropped on `uninstall --purge`). |

**Version adapters** — a flow bound to a version range as an *ordered list of steps* (adapters can
add/remove/reorder steps, not just swap selectors):

| Member | Signature | What it does |
| --- | --- | --- |
| `VersionAdapter` | `VersionAdapter(version_range, steps, name=None)` | One flow implementation for one version range. `steps` are `step(ctx) -> str` callables. |
| `resolve_adapter` | `resolve_adapter(adapters, version) -> VersionAdapter` | First range that matches; raises `NoAdapterError` (no fallback — never a blind tap). |
| step helpers | `open_app(pkg=None)`, `tap(text)`, `tap_if_present(text)`, `wait_for(text)`, `assert_absent(text)`, `press(key)`, `sleep(s)`, `shell(cmd)` | Build adapter step lists that read like the flow. `tap_if_present` is the "a new version added an optional dialog" primitive. |
| `AppDriver` | `AppDriver(slug, package, adapters, supported_versions=None, ceiling_for=None)` | `.run(flow, device_id)` resolves the adapter for *this device's* installed version and runs its steps. |

**Version policy** — a per-device ceiling:

| Member | Signature | What it does |
| --- | --- | --- |
| `make_ceiling_resolver` | `make_ceiling_resolver(config_getter, *, global_key="max_app_version", per_device_key="device_max_versions")` | Build a `ceiling_for(device_id)` from config (per-device override wins, else global). |
| `exceeds_ceiling` / `over_ceiling` | | Compare a version to a ceiling *at the ceiling's precision* (so `12` pins the whole 12.x line). |

**Fail-loud, never tap.** `AppDriver.run` runs a three-gate funnel and raises a *distinct*
`AppDriverError` subclass for each unsupported outcome, before any step runs:

| Exception | When |
| --- | --- |
| `AppNotInstalled` | The app isn't on the device — provision first. |
| `AppVersionUnsupported` | Installed version is outside the extension's `supported_versions`. |
| `VersionPolicyError` | Installed version exceeds this device's `max_app_version` ceiling (policy, not drift). |
| `NoAdapterError` | No adapter's range matches this version for the flow. |
| `ProvisionError` | Checksum mismatch or install failure during `provision`. |

```python
import devicekit_sdk
from devicekit_sdk.appdriver import VersionAdapter, AppDriver, open_app, tap, tap_if_present, wait_for

ADAPTERS = {"connect": [
    VersionAdapter(">=12.0.0 <13.0.0", [open_app(), tap("Connect"), wait_for("Connected")], name="12.x"),
    VersionAdapter(">=13.0.0 <14.0.0", [open_app(), tap("Connect"),
                                        tap_if_present("Allow"),           # 13.x consent dialog
                                        wait_for("Connected")], name="13.x"),
]}
driver = AppDriver("my-vpn", "com.example.vpn", ADAPTERS, supported_versions=">=12.0.0 <14.0.0",
                   ceiling_for=devicekit_sdk.appdriver.make_ceiling_resolver(lambda: devicekit_sdk.config("my-vpn")))
driver.run("connect", device_id)   # picks the right adapter for THIS device; raises loud if drifted
```
