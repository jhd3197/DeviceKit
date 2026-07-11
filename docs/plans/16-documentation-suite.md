# Plan 16 — Documentation Suite

**Status:** 🚧 in progress — Phases 1–2 ✅
**Inspired by:** ServerKit ships a real docs *system*, not a pile of markdown — a
navigable site, an extension author guide, an SDK reference, a fleet/agent contract, and
ADRs that record *why* the architecture is the way it is. DeviceKit has grown the same
surface area (extension platform, SDK, agent protocol, FQL, jobs, notifications) but its
docs are scattered, uneven, and half-hidden: `docs/EXTENSIONS.md` is excellent yet isn't
even linked from the README's documentation table.
**Depends on:** nothing hard — documents what plans 01–15 already shipped. Best done
*after* plan 15 lands so the browser/explorer/notification extensions can be the worked
examples throughout.

## The questions this plan answers

- **"How do extensions work / what's in the SDK?"** Today the only answer is one
  794-line file (`docs/EXTENSIONS.md`) that a newcomer has to read end-to-end. This
  plan keeps that guide but splits out the reference material (SDK surface, manifest
  field table, permission model) so it's *lookup-able*, not just readable, and adds the
  on-ramp that's missing: a "your first extension in 10 minutes" tutorial built on the
  `new_extension.py` scaffolder.
- **"What actually is DeviceKit and how do the four pieces talk?"** The architecture
  diagram + connection flow live only in `ROADMAP.md` (a 460-line changelog nobody
  reads for orientation). Extract a real `docs/ARCHITECTURE.md` — the mixin-composed
  backend, the agent HTTP/UDP protocol, droidlink, the frontend SSE model — as the
  single "read this first" doc.
- **"What's the agent ↔ backend contract?"** ServerKit has `FLEET_CONTRACT.md`;
  DeviceKit's equivalent (register/heartbeat/state/commands, HMAC signing from plan 07,
  capability map) is only discoverable by reading Kotlin and Python side by side. Write
  it down — it's the spec anyone building a non-Kotlin agent or debugging enrollment
  needs.
- **"Why is it built this way?"** The interesting decisions — extensions run in-process
  (not sandboxed), third-party frontend code is *not* loaded, droidlink kept its name
  instead of `devicekit` on PyPI, state moved from in-memory to SQLAlchemy — are
  currently folklore in commit messages and plan prose. Capture them as short ADRs so
  the *reasoning* survives, the way ServerKit's `docs/adr/` does.
- **"Do we want a docs site?"** Yes, eventually — but content first. This plan writes
  the markdown so it stands alone in-repo, and *optionally* wires a static site
  generator over it in the last phase. Getting the site scaffold before the content is
  the classic docs mistake.

## What exists today (the starting point)

- `docs/EXTENSIONS.md` — strong extension author guide (manifest, contribution points,
  SDK, permissions, lifecycle, registry, scaffolding, security posture). **Keep it**;
  refactor lightly.
- `docs/ci-setup.md` — CI/device-fixtures guide. Fine as-is.
- `prompture_integration.md` (repo root) — AI agent architecture. Fold into the docs
  tree.
- `ROADMAP.md` — carries the architecture diagram + connection flow that belong in a
  dedicated doc.
- `docs/plans/*` — the numbered improvement plans (this file's neighbors). These are
  *internal planning*, not user docs — leave them where they are; the docs suite links
  to them under a "Design & history" heading, doesn't absorb them.

Gaps: no getting-started/install walkthrough as a doc, no architecture doc, no SDK
*reference* (vs. the narrative guide), no fleet/agent protocol contract, no ADRs, no
droidlink usage doc separate from its own repo's README, README docs table is stale.

## Target structure

```
docs/
  README.md                 # docs index — the map (linked from root README)
  getting-started.md        # install → run backend → connect a device → first automation
  ARCHITECTURE.md           # the four components + data flow (extracted from ROADMAP)
  FLEET_CONTRACT.md         # agent ↔ backend protocol: register/heartbeat/state/commands + HMAC + capabilities
  extensions/
    guide.md                # today's EXTENSIONS.md, trimmed to narrative + how-to
    tutorial.md             # NEW: first extension in 10 min, on new_extension.py
    sdk-reference.md        # NEW: devicekit_sdk surface as a lookup table
    manifest-reference.md   # NEW: every extension.json field, extracted from validate_manifest
  ai-agent.md               # prompture_integration.md, moved + refreshed (tools, gate, session modes)
  droidlink.md             # using the pip library against a fleet (points at the droidlink repo for API detail)
  adr/
    0001-in-process-extensions.md
    0002-no-third-party-frontend-code.md
    0003-sqlalchemy-source-of-truth.md
    0004-droidlink-name-on-pypi.md
    0005-extension-ai-tools-always-gated.md
```

Nothing here is invented lore — every doc describes shipped code, and each ADR records a
decision already visible in the plans/commits (03/04, 13, 14). The point is to make the
*why* and the *reference* first-class instead of archaeological.

## Contribution points as the running example

Because plan 15 ships three real extensions, the extension docs should use them as
worked examples rather than toy snippets: `devicekit-browser` for a wire-protocol
blueprint + AI tools, `devicekit-explorer` for a builtin frontend contribution,
`devicekit-notification-capture` for owned tables + jobs + bus forwarding. That keeps
the docs honest (they describe code that exists) and doubles as review pressure on those
extensions' APIs.

## Phases

| Phase | Delivers | Notes |
|---|---|---|
| 1 ✅ | `docs/README.md` index + `getting-started.md` + fix root README docs table | The on-ramp. Everything else hangs off the index. |
| 2 ✅ | `ARCHITECTURE.md` (extract from ROADMAP) + `FLEET_CONTRACT.md` | The two "how the system works" docs. ROADMAP keeps a short diagram + a link. |
| 3 | Split `EXTENSIONS.md` → `extensions/guide.md` + `manifest-reference.md` + `sdk-reference.md`; add `tutorial.md` | Reference vs. narrative. Old path redirects/points to the new tree so external links don't rot. |
| 4 | `ai-agent.md` (from `prompture_integration.md`) + `droidlink.md` + the five ADRs | The remaining subsystems + decision records. |
| 5 | *(optional)* Static site generator over `docs/` (MkDocs Material or Docusaurus) + a `docs` CI check for dead links | Content-first: only after phases 1–4 read well as plain markdown. |

Phases 1–4 are independent enough to parallelize per-doc with subagents; phase 5 is
opt-in and last.

## Decisions to make while executing (log the choice, don't stop)

- **Docs site generator (phase 5):** MkDocs Material (Python, trivial, matches the
  backend toolchain) vs. Docusaurus (React, matches the frontend, heavier). Lean MkDocs
  unless the site needs React components. Defer entirely if phase 5 is skipped.
- **Where droidlink docs live:** the library has its own repo + PyPI README. `docs/droidlink.md`
  here should be *fleet-usage-oriented* (connect to a DeviceKit-managed device, run an
  automation from Python) and link out for the full API, not duplicate the library's
  reference — avoid two sources of truth that drift.
- **EXTENSIONS.md path:** external links (and CLAUDE-context memories) point at
  `docs/EXTENSIONS.md`. Either keep that path as the guide and add the reference files
  beside it, or move it and leave a one-line stub pointing to the new location. Prefer
  the stub-and-move so the tree is clean.

## Out of scope

- **Auto-generated API reference** (OpenAPI/Swagger for the backend routes). Worth doing
  eventually, but it's a code-annotation project, not a writing project — its own future
  plan.
- **Screenshots / video / a hosted docs domain.** Content and structure first; polish and
  hosting are a follow-up once the markdown is stable.
- **The numbered plan docs.** They stay internal design history; the suite links to them,
  doesn't rewrite them into user docs.
