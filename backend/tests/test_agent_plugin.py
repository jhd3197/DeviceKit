"""Plan 25 part 5 — agent-plugin manifest contract (schema only): validation, typed
permissions, resource limits, dependency-graph resolution, and the deferred-runtime stub."""
import pytest

from devicekit.agent_plugin.manifest import validate_plugin_manifest, AgentPluginError
from devicekit.agent_plugin.graph import resolve_order, DependencyError
from devicekit.mixins.agent_plugin import AgentPluginMixin


_VALID = {
    "name": "battery-guard",
    "version": "1.0.0",
    "description": "watches battery health",
    "capabilities": {
        "metrics": [{"name": "battery_health", "unit": "%", "interval_seconds": 60}],
        "health_checks": [{"key": "battery_ok", "title": "Battery OK"}],
        "commands": [{"name": "recalibrate"}],
    },
    "permissions": {
        "filesystem": [{"path": "/sys/class/power_supply", "mode": "read"}],
        "system": ["battery"],
    },
    "resources": {"max_memory_mb": 64, "max_cpu_percent": 10},
    "dependencies": [],
}


# ----------------------------------------------------------------- manifest validation
def test_valid_manifest_normalizes_all_sections():
    out = validate_plugin_manifest(_VALID)
    assert out["name"] == "battery-guard"
    # Every capability/permission section present (empty where omitted).
    assert set(out["capabilities"]) == {"metrics", "health_checks", "commands",
                                        "scheduled_tasks", "event_hooks"}
    assert set(out["permissions"]) == {"filesystem", "network", "process", "system"}


def test_missing_required_fields_raise():
    with pytest.raises(AgentPluginError) as ei:
        validate_plugin_manifest({"description": "no name/version"})
    assert any("name" in e for e in ei.value.errors)
    assert any("version" in e for e in ei.value.errors)


def test_bad_filesystem_permission_mode_rejected():
    m = dict(_VALID, permissions={"filesystem": [{"path": "/x", "mode": "execute"}]})
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(m)


def test_filesystem_permission_requires_path_and_mode():
    m = dict(_VALID, permissions={"filesystem": [{"path": "/x"}]})
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(m)


def test_resource_bounds_enforced():
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(dict(_VALID, resources={"max_cpu_percent": 250}))
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(dict(_VALID, resources={"max_memory_mb": 0}))


def test_unknown_top_level_key_rejected():
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(dict(_VALID, runtime="python"))


def test_self_dependency_rejected():
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(dict(_VALID, name="a", dependencies=["a"]))


def test_bad_name_pattern_rejected():
    with pytest.raises(AgentPluginError):
        validate_plugin_manifest(dict(_VALID, name="Bad Name!"))


# --------------------------------------------------------------------- dependency graph
def _m(name, deps):
    return {"name": name, "version": "1", "dependencies": deps}


def test_resolve_order_respects_dependencies():
    order = resolve_order([_m("c", ["b"]), _m("b", ["a"]), _m("a", [])])
    assert order.index("a") < order.index("b") < order.index("c")


def test_resolve_order_is_deterministic():
    plugins = [_m("b", []), _m("a", []), _m("c", [])]
    assert resolve_order(plugins) == ["a", "b", "c"]


def test_missing_dependency_raises():
    with pytest.raises(DependencyError):
        resolve_order([_m("a", ["ghost"])])


def test_cycle_detected():
    with pytest.raises(DependencyError):
        resolve_order([_m("a", ["b"]), _m("b", ["a"])])


# ------------------------------------------------------------------------- stateful mixin
class _Plugins(AgentPluginMixin):
    pass


def test_declare_and_list(fresh_db):
    c = _Plugins()
    c.declare_agent_plugin(_VALID)
    plugins = c.list_agent_plugins()
    assert len(plugins) == 1
    assert plugins[0]["name"] == "battery-guard"


def test_declare_upserts_by_name(fresh_db):
    c = _Plugins()
    c.declare_agent_plugin(_VALID)
    c.declare_agent_plugin(dict(_VALID, version="2.0.0"))
    plugins = c.list_agent_plugins()
    assert len(plugins) == 1
    assert plugins[0]["version"] == "2.0.0"


def test_declare_invalid_raises(fresh_db):
    c = _Plugins()
    with pytest.raises(AgentPluginError):
        c.declare_agent_plugin({"version": "1"})


def test_resolve_order_over_declared(fresh_db):
    c = _Plugins()
    c.declare_agent_plugin(_m("base", []))
    c.declare_agent_plugin(_m("ext", ["base"]))
    res = c.resolve_agent_plugin_order()
    assert res["order"].index("base") < res["order"].index("ext")


def test_resolve_order_reports_cycle(fresh_db):
    c = _Plugins()
    c.declare_agent_plugin(_m("a", ["b"]))
    c.declare_agent_plugin(_m("b", ["a"]))
    res = c.resolve_agent_plugin_order()
    assert "error" in res


def test_install_is_a_deferred_stub(fresh_db):
    c = _Plugins()
    c.declare_agent_plugin(_VALID)
    result = c.install_agent_plugin("battery-guard")
    assert result["installed"] is False
    assert "not implemented" in result["error"]
