"""Agent-plugin manifest contract (plan 25 part 5).

Adopts ServerKit's agent-plugin *schema* — capabilities, typed permissions, resource limits,
and a dependency graph — as a **declaration** DeviceKit can validate and reason about. The
on-device runtime is deliberately deferred (ServerKit's own ``install_plugin`` is a stub, and
real sandboxed code-on-agent is greenfield in both projects). This package is the contract;
``manifest`` validates it and ``graph`` resolves the dependency order.
"""
