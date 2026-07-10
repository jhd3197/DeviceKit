# Plan 14 — `devicekit` Python Package (droidlink → devicekit)

**Status:** proposed
**Inspired by:** ServerKit's packaging polish (the `serverkit` CLI, release discipline) —
but mostly driven by brand unification: one name across the platform, the library, and pip
**Depends on:** nothing — fully independent of the other plans

## The questions this plan answers

- **"Can I do a devicekit in Python?"** Yes — it already exists. `droidlink/` *is* the
  DeviceKit Python library: device control over USB/WiFi via the agent, 20+ manager
  modules (files, shell, input, screen, apps, clipboard, notifications, metrics, UI
  automation, gestures, logcat, intents, settings, contacts, streaming, events), UDP
  auto-discovery, a CLI (`cli.py`), and a pytest plugin with `device`/`device_pool`
  fixtures. This plan renames and publishes it; it does not build anything new.
- **"pip install devicekit?"** The name is **available on PyPI** (checked 2026-07-09:
  `pypi.org/pypi/devicekit/json` → 404; `droidlink` was never published either, so there
  are no external users to break). Claim it early — publish a 0.1.x as soon as the
  rename lands; available-today is not available-forever.
- **"Do I need a `devicekit-pip` GitHub repo?"** **No.** The PyPI project name is
  completely independent of the GitHub repo name — `pip install devicekit` can build and
  publish from a subdirectory of this monorepo. That keeps the "all in one" goal: one
  repo (`DeviceKit`), one brand, one `pip install devicekit`. Only if the library ever
  needs its own release cadence/issue tracker would you split it out, and the naming
  convention for that would be `devicekit-python` — but don't split now.

## Rename map

| Today | After |
|---|---|
| `droidlink/` (top-level dir) | `devicekit-py/` |
| `droidlink/droidlink/` (package) | `devicekit-py/devicekit/` |
| `pyproject.toml` → `name = "droidlink"` | `name = "devicekit"` |
| console script `droidlink = droidlink.cli:main` | `devicekit = devicekit.cli:main` |
| pytest entry `droidlink = droidlink.pytest_plugin` | `devicekit = devicekit.pytest_plugin` |
| `import droidlink` | `import devicekit` |
| `DroidLinkReporter` | `DeviceKitReporter` |

Already-branded pieces that need **no change**: the plugin's CLI flags
(`--devicekit-url`, `--devicekit-api-key`), the pyproject description ("…via DeviceKit
agent"), the agent protocol.

In-repo callers to update in the same commit: `.github/workflows/device-tests.yml`,
`docs/ci-setup.md`, root `README.md`, and any `conftest.py` examples. droidlink was
never on PyPI and this is a monorepo — **no compatibility shim**; fix all callers in
one commit and note the rename in the README.

## The name-shadowing gotcha (decide consciously)

`backend/devicekit/` is *also* a Python package named `devicekit` (the server's mixins).
Two packages with one import name can never be installed into the same environment.
Rules until unified:

1. **Never `pip install devicekit` into the backend's venv.** The backend imports its
   local package; an installed lib of the same name invites shadowing confusion.
2. CI/test environments that install the lib (device tests, user projects) don't run
   the backend from source — that's already true today, keep it true.

**Long-term "all in one" option (explicitly out of scope here):** invert the
dependency — the pip `devicekit` package becomes the shared device-control core, the
backend's `adb.py`/`uiautomator.py`/agent-HTTP code delegates to it, and the backend
package renames (e.g. `devicekit_server`). That would make the library the single
source of device-control truth. It's a separate project with real churn; write its own
plan if/when wanted.

## Publishing pipeline

1. **Version:** pyproject is the single source; expose `devicekit.__version__` via
   `importlib.metadata`.
2. **Build:** `python -m build` inside `devicekit-py/`.
3. **Publish:** GitHub Actions using **PyPI Trusted Publishing (OIDC)** — no long-lived
   API tokens. Trigger on tags matching `py-v*` (`py-v0.1.0`), building only the
   subdirectory. Add a `TestPyPI` dry-run job on workflow_dispatch.
4. **PyPI page:** the package README needs a quickstart —
   `pip install devicekit` → connect over USB → screenshot → run a pytest with the
   `device` fixture — plus links back to this repo. Add trove classifiers
   (`Programming Language :: Python :: 3`, `Topic :: Software Development :: Testing`,
   `Operating System :: OS Independent`) and keep the dependency footprint as-is
   (`requests` only — a genuine selling point).

## Phases

> **Status (2026-07-09):** Phase 1 ✅ complete — executed early to claim the PyPI name.
> Wire-protocol strings (`DROIDLINK_DISCOVER`, `DROIDLINK_DEVICE:`, `droidlink_frame`)
> deliberately kept for deployed-agent compatibility. Phase 3 ✅ (root README +
> ci-setup updated in the same commit).
>
> **Decision update (2026-07-09):** superseding the "no separate repo" answer above —
> the library moved to its own public repo (`github.com/jhd3197/devicekit-py`, local
> sibling clone) so it can be public and publish to PyPI while DeviceKit stays
> private. The monorepo no longer contains `devicekit-py/`; its device-tests workflow
> installs `devicekit` from PyPI. Phase 2 ✅ in that repo: trusted-publishing GitHub
> Actions workflow on `v*` tags (first 0.1.0 upload done manually to claim the name).

1. Rename: directory, package, pyproject (name/scripts/entry points), imports,
   `DeviceKitReporter` class, CI workflow, docs, README quickstart.
2. Publish workflow with trusted publishing; tag `py-v0.1.0`; verify
   `pip install devicekit` from PyPI on a clean environment.
3. Docs pass: root README gets a "Python library" section leading with
   `pip install devicekit`; `docs/ci-setup.md` examples updated; note the rename.
4. *(Optional, later, own plan)* Dependency inversion: backend consumes the library;
   backend package rename.

## Definition of done

On a clean machine: `pip install devicekit` succeeds; `import devicekit` and
`devicekit --help` work; `pytest --device <serial>` auto-loads the renamed plugin and
the `device` fixture; the device-tests workflow is green using the renamed package; the
PyPI project page shows the quickstart README.
