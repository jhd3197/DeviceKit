# ADR 0004 — The Python library kept the `droidlink` name on PyPI

- **Status:** Accepted
- **Date:** 2026-07-09
- **Recorded in:** [plan 14 — devicekit python package](../plans/14-devicekit-python-package.md);
  [ROADMAP Phase 34](../../ROADMAP.md).

## Context

The plan's original goal was brand unification: one `devicekit` name across the platform, the
library, and the pip package. PyPI was believed available (a 2026-07-09 check of
`pypi.org/pypi/devicekit/json` returned 404), and the full rename map — directory, package,
`pyproject` name/scripts/entry points, imports, `DroidLinkReporter → DeviceKitReporter` — was
specced and executed.

## Decision

The Python client library **kept its original `droidlink` brand**. It is published as
[`droidlink` 0.1.0](https://pypi.org/project/droidlink/) (`pip install droidlink`), extracted to its
own public repo [jhd3197/droidlink](https://github.com/jhd3197/droidlink). The `devicekit` rename
was **reverted**.

## Rationale

PyPI's **name-similarity policy rejects the bare name `devicekit`** — it is "too similar to an
existing project," the unrelated `device-kit` package. The rule applies to everyone, so nobody
(including us) can claim `devicekit`; the name can't even be squatted for later. Rather than ship an
awkward suffixed variant, keeping the already-publishable `droidlink` brand was the clean path.

## Consequences

- The library lives in its own repo and publishes via **PyPI Trusted Publishing (OIDC)** on `v*`
  tags. The monorepo installs `droidlink` from PyPI rather than vendoring it.
- **Wire and protocol strings were never renamed** — the pytest plugin keeps its `DROIDLINK_*` env
  vars and `DroidLinkReporter`, while the user-facing platform flags (`--devicekit-url`,
  `--devicekit-api-key`) still point at the DeviceKit backend.
- This also avoids the `backend/devicekit/` import-name shadowing gotcha the rename would have
  introduced.

## Alternatives considered

- **A suffixed variant** (`devicekit-py`) — rejected as an ugly compromise.
- **Squatting `devicekit`** — impossible under the policy.
- **A separate `devicekit-pip` repo** — unnecessary; the PyPI name is independent of the repo name.
