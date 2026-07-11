# ADR 0001 — Extensions run in-process, not sandboxed

- **Status:** Accepted
- **Recorded in:** [plan 03 — extension platform backend](../plans/03-extension-platform-backend.md);
  the trust model is documented in the [Extension Guide](../extensions/guide.md#security-posture--not-a-sandbox).

## Context

DeviceKit needed an extension platform that could contribute automation step types, FQL fields, AI
tools, routes, jobs, and tables. Both DeviceKit and its ancestor ServerKit are Flask apps, and
ServerKit's plugin mechanism (with its own "not-a-sandbox" ADR) ports almost directly: an
extension's backend package is hot-loaded into the running app with `importlib`. The audience is
self-hosters and CI device labs running their own instance.

## Decision

Extensions **load and run in-process** inside the Flask backend, with the host's full privileges.
The permission gate (`devicekit_sdk.require_permission(slug, cap)`) is **declaration-based
enforcement only** — it raises if the manifest didn't declare a capability, and nothing more. There
is deliberately no isolation boundary.

## Rationale

For a self-hosted device platform this is an acceptable v1 posture. In-process keeps the mechanism a
near-verbatim port of a proven design; contribution points become trivial in-memory dict
registrations; and it avoids the cost and complexity of out-of-process IPC. Safety is instead
*layered* from mechanisms that actually hold, not from a boundary the design can't honestly claim.

## Consequences

Because there is no sandbox, safety comes from four other layers:

- a **curated registry** (`devicekit-extensions`, CI-gated);
- a **consent card** showing exactly the declared `permissions` (unknown ones flagged as an
  "unknown" badge);
- a **pinned sha256** so installed bytes equal previewed bytes (mismatch is a hard failure);
- **Zip-Slip defense** on every archive entry, and **gated pip** — an extension's `requirements.txt`
  is never installed unless the operator sets `DEVICEKIT_ALLOW_EXTENSION_PIP`.

Disable-without-restart is handled by a `before_request` 503 status guard. The honest guidance:
**treat installing an extension like running any third-party code on the host.** A true isolation
boundary is a possible future escalation, not v1.

## Alternatives considered

- **Out-of-process isolation / a real sandbox** — rejected for v1 as disproportionate to the
  audience and cost; left as a future option.

## Related

[ADR 0002](0002-no-third-party-frontend-code.md) (the frontend half of the same trust model),
[ADR 0005](0005-extension-ai-tools-always-gated.md) (why extension AI tools never get unattended
hardware access, precisely *because* extensions are unsandboxed).
