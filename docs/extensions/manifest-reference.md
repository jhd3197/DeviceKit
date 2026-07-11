# Manifest Reference — `extension.json`

Every `extension.json` field, its rule, and its default — a lookup table, not prose. These rules
are enforced by `validate_manifest` (`backend/devicekit/extension_manifest.py`), which is the
**single source of truth**: the installer, the scaffolder's `--validate` mode, and
`GET /extensions/manifest-spec` all run it, so they can't drift.

For the *why* behind each contribution point, read the [Extension Guide](guide.md). For the SDK
those refs resolve to, the [SDK Reference](sdk-reference.md).

The manifest is the only required file, and it must sit at the **archive root**.

---

## Fields

| Field | Required? | Rule | Default |
| --- | --- | --- | --- |
| `name` | **Yes** | Slug; must match `^[a-zA-Z0-9_-]+$`. | — |
| `display_name` | **Yes** | Non-empty. | — |
| `version` | **Yes** | Loose semver: `MAJOR.MINOR[.PATCH][-pre]` (e.g. `1.0.0`, `1.2`, `1.0.0-rc1`). | — |
| `category` | No | One of `automation`, `monitoring`, `integration`, `ai`, `utility`. | `utility` |
| `description` | No | Free text (not validated). | — |
| `author` | No | Free text (not validated). | — |
| `permissions` | No | A list; each item a known capability (see [Permissions](#permissions)). | `[]` |
| `min_devicekit_version` | No | Version gate lower bound (see [Version gate](#version-gate)). | — |
| `max_devicekit_version` | No | Version gate upper bound. | — |
| `entry_point` | No | `module:attr` — a Flask `Blueprint`. | — |
| `url_prefix` | No | String starting with `/`. | `/extensions/<slug>` |
| `models` | No | `module:attr` — owns `ext_<slug>_*` tables. | — |
| `step_types` | No | `module:attr` — returns `{type_name: {label, category, config, execute}}`. | — |
| `fql_fields` | No | `module:attr` — returns `{field_name: spec}`. | — |
| `ai_tools` | No | `module:attr` — registers Prompture tools. | — |
| `provides` | No | `module:attr` — registers a sibling-callable surface (see [Extension dependencies](#extension-dependencies)). | — |
| `requires_extensions` | No | Object of `sibling-slug -> version range` (see [Extension dependencies](#extension-dependencies)). | `{}` |
| `device_requirements` | No | Object `{package, supported_versions?, provision?}` — the third-party app an app-driver extension drives (see [App-driver requirements](#app-driver-requirements)). | — |
| `lifecycle` | No | Object of `phase -> "module:func"`. | — |
| `jobs` | No | List of `{kind, handler: "module:func"}`. | — |
| `schedules` | No | List of `{name, kind, ...}`. | — |
| `config_schema` | No | Object of `field -> spec`. | — |
| `automation_templates` | No | List of paths (relative to the backend dir). | — |
| `contributions` | No | Object of frontend contribution kinds (see [Contributions](#contributions)). | — |

The `module:attr` form must match `^[A-Za-z_][\w.]*:[A-Za-z_]\w*$` — e.g. `routes:bp` means
attribute `bp` in module `routes`, resolved under `devicekit.extensions.<slug_underscored>.`.

---

## Validation behavior — what raises when

`validate_manifest` returns `True` or raises `ManifestError`. Two error tiers:

**Raise immediately** (before any other check):

1. The manifest is not a JSON object → `"Manifest must be a JSON object"`.
2. Any of `name` / `display_name` / `version` missing or falsy →
   `"Manifest missing required fields: ..."`.
3. `name` is not a string or fails the slug regex →
   `"Extension name must be alphanumeric/dashes/underscores: ..."`.

**Accumulate, then raise once** — every other shape problem is collected so you see them all at
once, ending with `"Manifest validation failed: <problems>. See GET /extensions/manifest-spec or
docs/EXTENSIONS.md."` This covers: bad `version` semver, unknown `category`, non-list or unknown
`permissions`, malformed `module:attr` refs, bad `lifecycle` / `jobs` / `schedules` /
`config_schema` / `automation_templates` / `url_prefix` shapes, and malformed `contributions`
entries.

**Unknown contribution kinds are tolerated** (forward-compat) — they never fail validation.

---

## Permissions

`permissions` is both a **consent step** at install (the card shows exactly what you declared) and
an **enforced gate** at call time via the SDK. The five known capabilities:

| Permission | Grants |
| --- | --- |
| `adb` | Raw `adb shell`, plus `adb forward` / `--remove` (via `device_control(...).shell/forward`). |
| `device.control` | Tap / press / screenshot on a device. |
| `filesystem` | Host filesystem access. |
| `network` | Outbound network (e.g. a webhook POST). |
| `llm` | LLM / AI calls. |

Anything outside this set is accepted into the manifest but flagged **unknown** on the consent card
(`permissions.unknown_permissions`). The gate is declaration-based, not a sandbox — see
[ADR 0001](../adr/0001-in-process-extensions.md).

---

## Version gate

`min_devicekit_version` / `max_devicekit_version` are checked by `assert_devicekit_compatible`
against the running platform version (`DEVICEKIT_VERSION`, currently **`1.0.0`**) — **at install
and at update**, not just first install. A manifest whose range excludes the running version is
rejected:

```
<name> v<version> needs DeviceKit <min>–<max> (this is 1.0.0).
```

Comparison is a loose numeric parse (leading integer run of each dotted/hyphenated segment),
inclusive on both bounds.

---

## Contributions

The `contributions` object declares frontend wiring (plan 04). Known kinds are shape-checked; each
entry must carry its required keys. Only **builtin** extensions actually ship the components these
reference — see [ADR 0002](../adr/0002-no-third-party-frontend-code.md).

| Kind | Entry shape (required keys) | Renders |
| --- | --- | --- |
| `nav` | list of `{label, route}` (plus optional `id`, `section`, `icon`) | sidebar item |
| `routes` | list of `{path, component}` | a route in a per-extension error boundary |
| `widgets` | list of `{slot, component}` | every `<ExtensionSlot>` matching `slot` |
| `command_palette` | list of `{label, action}` | a `Ctrl+K` palette entry |
| `page_titles` | object of `{ "/path": "Title" }` | `document.title` for that path |

Seed widget slots: `dashboard.top`, `node-detail.tabs`, `run-detail.panels`, `settings.panels`.
`icon` is an inline SVG string, sanitized before injection.

---

## Extension dependencies

An extension can depend on — and call — another extension (plan 17). Two manifest keys, one on
each side of the relationship:

**Consumer side — `requires_extensions`.** A map of sibling slug → loose version range, ANDed:

```json
"requires_extensions": { "devicekit-browser": ">=0.1.0" }
```

Ranges accept `>=`, `>`, `<=`, `<`, `==`/`=`, a bare version (treated as `>=`), `*`/empty (any),
and space/comma-separated constraints (`">=1.0 <2.0"`). The matcher (`range_satisfies`) reuses the
same loose numeric parse as the version gate. Enforced by `assert_required_extensions` **at install
and update**: if a required sibling is missing or its installed version is out of range, the install
is refused with `<name> requires '<slug>' ...` before anything is written. Preview
(`POST /extensions/preview`) returns `requires_extensions` and folds any unmet dependency into its
`warnings`, so the consent UI can offer to install the chain.

**Provider side — `provides`.** A `module:attr` whose function receives an `sdk.provides(slug)`
binder and registers the curated callables siblings may invoke:

```json
"provides": "api:register"
```

```python
# api.py
def fetch(pool="default", url=None, fmt="html"):
    ...
def register(api):
    api.method(fetch)              # exposes devicekit-browser's fetch to siblings
```

A consumer reaches it with `devicekit_sdk.extension("<slug>").<method>(...)` — dispatched
**in-process** (no HTTP hop) but gated on the provider being *active*, so a disabled provider raises
`ExtensionUnavailable` rather than failing deep in a call. See the
[SDK Reference](sdk-reference.md#sibling-extensions-plan-17).

**Lifecycle.** Uninstalling an extension is **blocked** while an active dependent still requires it
(`DELETE /extensions/<slug>` → `409`; pass `?force=1` to override). Disabling a depended-on
extension only *warns* — dependents keep running and degrade via `ExtensionUnavailable`. The registry
mirrors `requires_extensions` as a `requires` field so the marketplace can show "requires
devicekit-browser" and installing from the registry pulls the chain in first.

---

## App-driver requirements

An **app-driver** extension automates a third-party app it doesn't ship. `device_requirements`
declares that relationship (plan 18):

```json
"device_requirements": {
  "package": "com.expressvpn.vpn",
  "supported_versions": ">=12.0.0 <14.0.0",
  "provision": "user_supplied_apk"
}
```

| Sub-field | Required? | Meaning |
| --- | --- | --- |
| `package` | **Yes** | The app the driver targets (checkable per device via `list_installed_apps`). |
| `supported_versions` | No | The loose version range the extension has adapters for. A device outside it is *known-unsupported* (surfaced, not blind-attempted). |
| `provision` | No | `user_supplied_apk` (default: user uploads the APK once, extension pins its sha256) or `play_store` (fire a `market://` intent — no pinning). |

Unlike `requires_extensions`, this is **not** enforced at install — the app may legitimately be
absent until the user provisions it. It is instead surfaced up front on the **consent card**
(`POST /extensions/preview` returns `device_requirements` and adds a "drives `<package>`…" warning),
and enforced **at drive time** by the [`appdriver`](sdk-reference.md#appdriver-app-driver-framework-plan-18)
framework. See the guide's [App-driver extensions](guide.md#app-driver-extensions-provision-and-drive-a-third-party-app-plan-18)
section for the full model.

---

## Data-table naming

Any table an extension owns **must** be prefixed `ext_<slug>_` with dashes converted to underscores
— that is exactly what `table_prefix(slug)` returns and what `uninstall?purge` drops:

```python
table_prefix("devicekit-webhook-notify")  # -> "ext_devicekit_webhook_notify_"
```

---

## The machine-readable spec

`GET /extensions/manifest-spec` returns the same rules as JSON (`manifest_spec()`): `required_fields`,
`slug_pattern`, `module_ref_pattern`, `categories`, `known_permissions`, `contribution_kinds`, a
`contribution_points` description map (including `device_requirements`), `provision_modes`, and
`devicekit_version`. Because it comes from the same constants the validator uses, it never drifts from
this table. Validate locally with the scaffolder:

```bash
python scripts/new_extension.py --validate builtin-extensions/devicekit-webhook-notify
```
