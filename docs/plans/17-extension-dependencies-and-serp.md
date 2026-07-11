# Plan 17 — Extension Dependencies + `devicekit-serp`

**Status:** 🚧 in progress (phases 1–2 ✅)
**Inspired by:** ServerKit's plugins compose — one plugin calls another's service rather
than reimplementing it. DeviceKit's plan 15 deliberately shipped `devicekit-browser`
first and deferred SERP with a named prerequisite: extensions can't yet depend on, or
call, other extensions. This plan builds that mechanism and then proves it with the
smallest possible consumer — search executed in a device's real Chrome.
**Depends on:** 15 (`devicekit-browser` must exist and be stable — SERP is a thin layer
over its pool-routed fetch). Soft: 16 (documents the dependency model).

## The questions this plan answers

- **"Can one extension use another's API?"** Not today. An extension gets `devicekit_sdk`
  (host seams) but no handle to a *sibling* extension. This plan adds two things: a
  `requires_extensions` manifest key (declare the dependency, enforced at install) and
  an SDK seam — `sdk.extension("<slug>")` — that returns a thin client for a sibling's
  registered surface. `devicekit-serp` becomes the first real user.
- **"What happens if the dependency isn't installed / is disabled?"** The failure has to
  be loud and early, not a mystery 503 mid-automation. Install refuses if a required
  extension is absent (with a clear "install devicekit-browser first" message); the
  status guard already flips a disabled extension's routes to 503, so a *runtime*
  disable of the dependency surfaces as a clean dependency-unavailable error, and
  uninstall of a depended-on extension is blocked (or warns) while a dependent is
  active.
- **"Why is SERP different from a normal API wrapper?"** A key-based SERP API is just an
  HTTP client — boring, and it leaks your server's IP. Running the search *on the
  device* through `devicekit-browser` means real-device fingerprint, real residential
  IP, pool rotation across the fleet, and no per-query API cost. The tradeoff is
  scraping fragility (Google's result DOM drifts), which this plan handles the same way
  a browser is meant to: resilient extraction with a clear "couldn't parse results"
  failure rather than silent empty output.

## Part 1 — The dependency mechanism (the platform work)

**Manifest key** — `requires_extensions`: a map of `slug → version range` (loose semver,
same matcher as `min/max_devicekit_version` in `extension_manifest.py`). Validated by
`validate_manifest`; an empty/absent map means no dependencies (unchanged behavior).

```json
"requires_extensions": { "devicekit-browser": ">=0.1.0" }
```

**Install-time enforcement** — in the install pipeline (`mixins/extensions.py`
`_install_from_buffer`), after manifest validation: resolve each required slug against
installed rows, check version satisfies the range, refuse install with a specific error
if missing/incompatible. This mirrors the existing `assert_devicekit_compatible` gate —
same shape, one level down (extension→extension instead of extension→host).

**The SDK seam** — `sdk.extension(slug)` returns a small client object, *not* a raw
Python import of the sibling's module (that would couple internals and bypass the status
guard). Two backing options, pick the one that fits how sibling surfaces are registered:

- **Preferred — registered-callable dispatch:** siblings already register `ai_tools`
  (name → func) in `_ext_ai_tools`. Expose a curated subset as a callable façade:
  `sdk.extension("devicekit-browser").fetch(pool="default", url=...)` dispatches to the
  browser extension's registered function *in-process*, but routed through a lookup that
  respects the sibling's active/disabled status (raises `ExtensionUnavailable` if not
  active). No HTTP hop, no serialization tax.
- **Fallback — internal HTTP:** call the sibling's blueprint over localhost. Simpler
  isolation, but pays serialization and needs an internal auth token. Only if in-process
  dispatch proves too coupled.

Go with in-process dispatch; it matches that extensions already share one process and
one DB (they're not sandboxed — ADR territory from plan 16).

**Lifecycle interactions** — teach enable/disable/uninstall (`mixins/extensions.py`) the
dependency graph: block (or warn-and-cascade, a decision to log) uninstalling an
extension that active dependents require; when a dependency is disabled, dependents keep
running but their `sdk.extension()` calls raise `ExtensionUnavailable` — which is
correct, and the dependent should degrade gracefully.

**Registry** — `registry_index.json` entries gain an optional `requires` field mirroring
the manifest, so the marketplace can show "requires devicekit-browser" and the installer
can offer to install the chain.

## Part 2 — `devicekit-serp` (the consumer that proves it)

**Category:** `integration` · **Permissions:** `network` ·
**Requires:** `devicekit-browser >=0.1.0`

Tiny by design — it owns *no* device code. Every device touch goes through
`sdk.extension("devicekit-browser")`:

1. `search(query, engine="google", count=10, pool="default")`:
   - build the engine URL (`google` / `bing` / `duckduckgo` — a small per-engine
     adapter of {search URL template, result selector set});
   - call `browser.fetch(pool, url)` — the browser extension picks a device round-robin,
     navigates, returns HTML + which `device_id` served it;
   - parse results out of the DOM (title, url, snippet) with the engine's selectors;
   - return `{query, engine, device_id, results: [...]}`.
2. Resilience: selectors live in the per-engine adapter so a Google DOM change is a
   one-file fix; parse-failure returns an explicit error (and optionally the raw HTML for
   debugging) rather than an empty list that looks like "no results."

**AI tool:** `devicekit_serp__search` (read — it mutates nothing on the device; the
underlying browser `fetch` is the gated write, and it's gated *there*, once). **Step
type:** `serp_search` — query in, results array into a step variable, so an automation
can "search → open first result → screenshot." **No frontend** (third-party extension;
backend + step type only, per the plan 04 boundary).

This is also the honest demonstration of *why* the dependency model matters: SERP is ~150
lines because browser already exists. Without `requires_extensions` it would have to
re-implement CDP-over-adb — the exact duplication the mechanism prevents.

## Phases

| Phase | Delivers | Proves |
|---|---|---|
| 1 ✅ | `requires_extensions` manifest key + `validate_manifest` support + install-time enforcement | dependencies declared and checked |
| 2 ✅ | `sdk.extension(slug)` seam (in-process dispatch + `ExtensionUnavailable`) + lifecycle graph (block/warn on uninstall, disable degradation) | siblings can call siblings safely |
| 3 | `devicekit-serp`: per-engine adapters → `search()` over `browser.fetch` → AI tool + step type | the mechanism works end-to-end on a real consumer |
| 4 | registry `requires` field + install-the-chain UX + EXTENSIONS.md dependency section | marketplace understands dependency graphs |

**Phase 1 — shipped.** `requires_extensions` (map of `slug → loose-semver range`) validated in
`validate_manifest`; `range_satisfies()` added to `extension_manifest.py` (reuses `_parse_version`,
supports `>= > <= < == =` and bare/`*`, ANDed). Install-time gate `assert_required_extensions()` in
`ExtensionsMixin` refuses install with a specific "install `<slug>` first" / version-mismatch message
(mirrors `assert_devicekit_compatible`); `missing_required_extensions()` + `active_dependents()` back
the gate, preview warnings, and (later) the lifecycle graph. Preview now returns `requires_extensions`
and folds unmet deps into `warnings`. Tests: `test_extension_dependencies.py`.

**Phase 2 — shipped.** Chose in-process dispatch (not internal HTTP). New SDK seam
`sdk.extension(slug)` returns a thin `_ExtensionClient` whose attribute access dispatches to the
sibling's registered method via `host.invoke_extension_api`, resolved fresh per call and gated on
the sibling being `active` — a disabled sibling raises `ExtensionUnavailable`, an unknown method
raises `AttributeError`. Provider side: manifest key `provides: "module:func"`, whose func gets an
`sdk.provides(slug)` binder (`api.method(fn)`), mirroring the `ai_tools` pattern; the surface is
tracked in `host._ext_extension_api[slug]`, reset on activation and torn down on
disable/uninstall. `devicekit-browser` now `provides` `fetch(pool, url, fmt)` (new `api.py`,
returns `{device_id, url, <fmt>}`) — its content sha256 + registry entry were updated. Lifecycle
graph: **block** (logged decision, not warn-and-cascade) uninstalling an extension while an active
dependent requires it (`force=True` / `?force=` overrides → route 409); disable only warns and lets
dependents degrade via `ExtensionUnavailable`. Tests extend `test_extension_dependencies.py`.

Phase 3 depends on 1+2; phases 1 and 2 are sequential (2 builds on 1's manifest key).

## Out of scope

- **App-driver / provisioning extensions** — declaring and installing a third-party APK,
  version-keyed behavior. That's plan 18; it's a *different* dependency (extension→device
  app, not extension→extension).
- **Dependency version *ranges* resolving to auto-upgrade** — if a dependent needs a
  newer sibling, this plan reports the conflict; it doesn't auto-bump. Keep upgrades
  user-driven.
- **Third-party (non-builtin) SERP frontend.** Unchanged boundary — no third-party
  frontend code loads.
