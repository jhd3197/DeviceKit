# ADR 0002 — Only builtin extensions ship frontend code

- **Status:** Accepted
- **Recorded in:** [plan 04 — extension platform frontend](../plans/04-extension-platform-frontend.md)
  ("The delivery decision").

## Context

Extensions want to contribute UI — nav items, pages, dashboard widgets. The question is how to load
third-party React code into the app. ServerKit weighed three options: (a) runtime, sha256-verified
ESM bundles via Blob URL + import map; (b) iframes; (c) pre-bundled builtins plus backend-only
third-party extensions. ServerKit shipped (c).

## Decision

Adopt ServerKit's **option (c)**: only **builtin / first-party** extensions ship frontend code, which
compiles into the app bundle. **Third-party extensions contribute backend + step types only** — and
still get UI for free.

## Rationale

The decision costs less in DeviceKit than it would elsewhere, because DeviceKit's best extension
surface — automation **step types** — already needs **zero frontend code**: the AutomationEditor
auto-renders each step's config form from `GET /automations/step-types`. So a third-party extension
with no custom pages is still fully useful. Custom pages remain a builtin privilege until runtime
loading is actually justified.

## Consequences

- Builtin frontends live at `builtin-extensions/<slug>/frontend/` as the source of truth, synced into
  the tracked `frontend/src/extensions/<slug>/` by `scripts/sync-builtin-frontends.mjs`, with a
  `--check` **CI drift gate**.
- Builtin frontends import host code only from the **versioned `devicekit-sdk` alias** — internal
  `src/` restructures never break extensions; only the SDK surface is contract.
- Extensions declare UI **declaratively** in the manifest; the backend merges every active
  extension's block into one envelope at `GET /extensions/contributions`, which the app renders
  dynamically (no `App.jsx` edits).
- Each contributed route/widget is wrapped in a **per-extension error boundary** (a broken extension
  never white-screens the app), and manifest SVG icons are **sanitized** before injection.
- `devicekit-explorer` is the first real user of a builtin frontend — a full page plus a NodeDetail
  tab.

## Alternatives considered

- **Runtime ESM bundles** — powerful, but risks React version skew across host and extension;
  ServerKit built the loader and left it dormant.
- **Iframes** — give isolation but lose shared theme and navigation; an escape hatch only.

## Related

[ADR 0001](0001-in-process-extensions.md) (the backend half of the trust model).
