# DeviceKit Documentation

The map for everything DeviceKit. Start with **[Getting Started](getting-started.md)** if you
just want it running, or **[Architecture](ARCHITECTURE.md)** if you want to understand how the
four pieces fit together before touching code.

DeviceKit is four components working as one platform: a **Python/Flask backend** that owns
device state and orchestration, a **React frontend** dashboard, a **Kotlin agent app** that runs
on each Android device, and **[droidlink](https://pypi.org/project/droidlink/)** — a Python
library for scripts and CI. This suite documents all four, plus the extension platform, the AI
layer, and the agent↔backend protocol.

---

## Start here

| Doc | What it answers |
| --- | --- |
| [Getting Started](getting-started.md) | Install → run the backend → connect a device → run your first automation. |
| [Architecture](ARCHITECTURE.md) | What DeviceKit actually is and how the four components talk. Read this first for orientation. |

## Reference

| Doc | What it answers |
| --- | --- |
| [Fleet Contract](FLEET_CONTRACT.md) | The agent ↔ backend protocol: register / heartbeat / state / commands, HMAC signing, pairing enrollment, capabilities. The spec for building a non-Kotlin agent or debugging enrollment. |
| [AI Agent](ai-agent.md) | The Prompture-backed per-device agent: tools, the confirmation gate, session modes (observe / supervised / autonomous), NL automation, self-healing. |
| [droidlink](droidlink.md) | Using the `pip install droidlink` library against a DeviceKit-managed fleet — connect, control, and run tests in CI. |
| [CI/CD Setup](ci-setup.md) | GitHub Actions integration, device fixtures, device locking, parallel testing. |

## Extensions

DeviceKit is a small core plus optional **extensions** that contribute step types, FQL fields,
AI tools, routes, jobs, and tables — most of it with zero frontend code.

| Doc | What it answers |
| --- | --- |
| [Extension Guide](extensions/guide.md) | The narrative author guide: anatomy, contribution points, lifecycle, install sources, the registry, security posture. |
| [First Extension Tutorial](extensions/tutorial.md) | Build and install your first extension in ~10 minutes on the `new_extension.py` scaffolder. |
| [Manifest Reference](extensions/manifest-reference.md) | Every `extension.json` field, its validation rule, and its default — a lookup table, not prose. |
| [SDK Reference](extensions/sdk-reference.md) | The `devicekit_sdk` surface as a lookup table: every export, signature, and the permission each device-control method requires. |

The worked examples throughout the extension docs are the four builtin extensions in
[`builtin-extensions/`](../builtin-extensions): `devicekit-webhook-notify` (the reference —
exercises every seam), `devicekit-browser` (CDP-over-adb + AI tools + a device pool),
`devicekit-explorer` (the first builtin frontend), and `devicekit-notification-capture`
(jobs + owned tables + bus forwarding).

## Decision records

Short ADRs recording *why* the architecture is the way it is — decisions already visible in the
plans and commits, captured so the reasoning survives.

| ADR | Decision |
| --- | --- |
| [0001](adr/0001-in-process-extensions.md) | Extensions run in-process, not sandboxed. |
| [0002](adr/0002-no-third-party-frontend-code.md) | Only builtin extensions ship frontend code. |
| [0003](adr/0003-sqlalchemy-source-of-truth.md) | SQLAlchemy is the single source of truth. |
| [0004](adr/0004-droidlink-name-on-pypi.md) | The Python library kept the `droidlink` name on PyPI. |
| [0005](adr/0005-extension-ai-tools-always-gated.md) | Extension AI tools are always gated. |

## Design & history

These are **internal planning**, not user docs — kept here so the suite links to them under one
roof, not absorbed into it.

- [ROADMAP.md](../ROADMAP.md) — the full development history, phase by phase.
- [docs/plans/](plans/00-overview.md) — the numbered improvement plans (the design docs behind
  every phase). The dependency graph and phase ordering live in the overview.

## Tooling

These docs render on GitHub as-is. Optionally, build them into a searchable static site with
[MkDocs Material](https://squidfunk.github.io/mkdocs-material/):

```bash
pip install -r docs/requirements.txt
mkdocs serve     # live preview at http://127.0.0.1:8000
mkdocs build     # static site into ./site
```

Link integrity is enforced in CI (`.github/workflows/docs.yml`) by a GitHub-relative-aware
dead-link checker you can also run locally:

```bash
python scripts/check_docs_links.py
```

---

> Docs describe **shipped code**. Every reference here maps to something in the repo today; where
> a subsystem's older design doc drifted from reality, the current doc says so. If you find a
> doc that disagrees with the code, the code is right — please
> [open an issue](https://github.com/jhd3197/DeviceKit/issues).
