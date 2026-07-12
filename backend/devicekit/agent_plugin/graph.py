"""Dependency-graph resolution for declared agent plugins (plan 25 part 5).

Pure graph logic over normalized manifests: a topological install order plus cycle and
missing-dependency detection. This is what a real runtime *would* consume to decide load
order; declaring it now (with the runtime deferred) is the point of the schema-only phase.
"""


class DependencyError(ValueError):
    """A dependency graph that can't be resolved (cycle or missing plugin)."""


def resolve_order(manifests):
    """Return plugin names in an order where every plugin comes after its dependencies.

    ``manifests`` is a list of normalized manifests (each ``{name, dependencies, ...}``).
    Raises ``DependencyError`` if a dependency names an undeclared plugin or if the graph has
    a cycle. Deterministic: ready nodes are emitted in sorted order so the result is stable.
    """
    by_name = {}
    for m in manifests:
        name = m["name"]
        if name in by_name:
            raise DependencyError(f"duplicate plugin declared: {name}")
        by_name[name] = list(m.get("dependencies") or [])

    for name, deps in by_name.items():
        for dep in deps:
            if dep not in by_name:
                raise DependencyError(
                    f"plugin '{name}' depends on undeclared plugin '{dep}'")

    # Kahn's algorithm with a stable (sorted) ready set.
    remaining = {n: set(d) for n, d in by_name.items()}
    order = []
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if not deps)
        if not ready:
            raise DependencyError(
                f"dependency cycle among: {sorted(remaining)}")
        for n in ready:
            order.append(n)
            del remaining[n]
        for deps in remaining.values():
            deps.difference_update(ready)
    return order
