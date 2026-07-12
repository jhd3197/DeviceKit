"""Pure rollout policy (plan 25 part 3): canary → staged → full, with rollback.

No DB, no time source of its own — the mixin passes ``now`` and live stats in, so this is
deterministic and unit-testable. Two jobs:

* **Cohort membership.** A device's cohort is a *stable* bucket derived from its id, so a
  rollout only ever widens: a device in the canary cohort is also in staged and full. That
  monotonicity is what makes "advance the stage" mean "offer to strictly more devices" with
  no device ever losing an offer it already had.
* **Advance/rollback decision.** After a stage's dwell elapses and the observed failure rate
  is acceptable, advance; if failures cross the threshold (with enough samples to be
  meaningful), roll back instead of pressing on. Crash-loop backoff on individual devices is
  enforced separately (per-device attempt caps in the mixin).
"""
import hashlib

STAGES = ["canary", "staged", "full"]

DEFAULT_ROLLOUT_CONFIG = {
    "canary_percent": 10,     # canary cohort: stable bucket < this
    "staged_percent": 50,     # staged cohort: stable bucket < this
    "dwell_seconds": 3600,    # minimum soak per stage before advancing
    "failure_threshold": 0.34,  # > ~1/3 of sampled devices failing → roll back
    "min_samples": 3,         # need at least this many terminal results to judge failure
}


def normalize_config(config):
    """Merge a partial rollout config over the defaults (unknown keys dropped)."""
    out = dict(DEFAULT_ROLLOUT_CONFIG)
    for k in DEFAULT_ROLLOUT_CONFIG:
        if config and k in config and config[k] is not None:
            out[k] = config[k]
    return out


def device_bucket(device_id):
    """Stable 0–99 bucket for a device id (sha256-derived, deterministic across processes)."""
    h = hashlib.sha256((device_id or "").encode("utf-8")).hexdigest()
    return int(h, 16) % 100


def in_cohort(device_id, stage, config):
    """Is ``device_id`` inside the cohort for ``stage``? Widens monotonically canary⊆staged⊆full."""
    config = normalize_config(config)
    bucket = device_bucket(device_id)
    if stage == "canary":
        return bucket < config["canary_percent"]
    if stage == "staged":
        return bucket < config["staged_percent"]
    if stage == "full":
        return True
    return False


def evaluate_rollout(stage, stage_entered_at, now, stats, config):
    """Decide what to do with a rollout at ``stage``.

    ``stats`` is ``{"installed": int, "failed": int}`` observed for this rollout. Returns one
    of: ``{"action": "rollback"}`` (failing), ``{"action": "hold"}`` (still soaking),
    ``{"action": "advance", "next_stage": ...}``, or ``{"action": "complete"}`` (full stage
    soaked cleanly). Rollback is checked before dwell so a bad release is pulled fast.
    """
    config = normalize_config(config)
    installed = int(stats.get("installed", 0))
    failed = int(stats.get("failed", 0))
    terminal = installed + failed
    if terminal >= config["min_samples"] and \
            failed / terminal >= config["failure_threshold"]:
        return {"action": "rollback", "reason":
                f"{failed}/{terminal} devices failed (>= {config['failure_threshold']:.0%})"}
    entered = now if stage_entered_at is None else stage_entered_at
    if (now - entered) < config["dwell_seconds"]:
        return {"action": "hold"}
    if stage == "full":
        return {"action": "complete"}
    idx = STAGES.index(stage) if stage in STAGES else 0
    return {"action": "advance", "next_stage": STAGES[idx + 1]}
