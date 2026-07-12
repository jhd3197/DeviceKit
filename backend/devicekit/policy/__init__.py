"""Desired-state fleet policy engine (plan 23).

``devicekit.yaml`` declares what a device (or group) *should* look like — apps at pinned
versions (plan 18), automation schedules (plan 22), device settings, and the extension set.
The pipeline mirrors ServerKit's manifest loop: **spec** (validate + normalize + hash) →
**persist** (``FleetPolicy`` row) → **plan** (pure desired-vs-live diff → ordered steps +
hard blockers) → **apply** (as a job, snapshotted, idempotent) → **drift** (periodic re-plan)
→ **scaffold** (render YAML *from* live state).

Pure logic lives here (spec, planner, scaffold); everything that touches live devices or the
DB lives in ``mixins/fleet_policy.py``.
"""
from devicekit.policy.spec import (
    PolicySpecError,
    load_policy,
    normalize_policy,
    policy_hash,
    effective_spec_for_device,
    dump_policy_yaml,
)

__all__ = [
    "PolicySpecError",
    "load_policy",
    "normalize_policy",
    "policy_hash",
    "effective_spec_for_device",
    "dump_policy_yaml",
]
