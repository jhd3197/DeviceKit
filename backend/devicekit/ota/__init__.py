"""OTA agent updates (plan 25 part 3): signed APK releases + rollout policy.

``signing`` holds the Ed25519 release-signing primitive (greenfield here — plan 29 was
never written, so OTA brings its own signing). ``rollout`` holds the pure cohort/advance
logic (canary → staged → full + rollback). The stateful surface (releases, rollouts,
per-device update state, agent-pull endpoints) lives on ``AgentOtaMixin``.
"""
