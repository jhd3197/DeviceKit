"""Plan 07 phase 4 — capability-driven targeting: FQL `can.*` / `android_api` fields and
the `require_capability` automation step."""
import pytest

from devicekit.mixins.fleet_query import FleetQueryMixin, parse_query, evaluate_ast
from devicekit.mixins.automation import _exec_require_capability


class _Fleet(FleetQueryMixin):
    def get_agent_capabilities(self, device_id):
        return _CAPS.get(device_id, {})


_CAPS = {}


def test_can_field_parses_with_dot():
    ast = parse_query("can.screen_record = true")
    assert ast is not None


def test_can_field_filters_devices():
    fleet = _Fleet()
    devices = [
        {"device_id": "d1", "capabilities": {"screen_record": True, "android_api": 34}},
        {"device_id": "d2", "capabilities": {"screen_record": False, "android_api": 31}},
    ]
    ast = parse_query("can.screen_record = true")
    matched = [d for d in devices if evaluate_ast(ast, d, fleet_mixin=fleet)]
    assert [d["device_id"] for d in matched] == ["d1"]


def test_android_api_comparison():
    fleet = _Fleet()
    devices = [
        {"device_id": "d1", "capabilities": {"android_api": 34}},
        {"device_id": "d2", "capabilities": {"android_api": 31}},
    ]
    ast = parse_query("android_api >= 33")
    matched = [d for d in devices if evaluate_ast(ast, d, fleet_mixin=fleet)]
    assert [d["device_id"] for d in matched] == ["d1"]


def test_can_field_resolves_via_fleet_mixin_when_not_inline():
    """A device dict without an inline capabilities map falls back to the registry."""
    fleet = _Fleet()
    _CAPS["dX"] = {"root": True}
    devices = [{"device_id": "dX"}]
    ast = parse_query("can.root = true")
    matched = [d for d in devices if evaluate_ast(ast, d, fleet_mixin=fleet)]
    assert len(matched) == 1


def test_capability_fields_advertised():
    fleet = _Fleet()
    fields = fleet.get_query_fields()
    assert "can.screen_record" in fields
    assert "android_api" in fields


class _Client:
    def __init__(self, caps):
        self._caps = caps

    def get_agent_capabilities(self, device_id):
        return self._caps


def test_require_capability_passes_when_present():
    c = _Client({"screen_record": True})
    out = _exec_require_capability(c, {"capability": "screen_record"}, "d1")
    assert "present" in out


def test_require_capability_fails_when_missing():
    c = _Client({"screen_record": False})
    with pytest.raises(ValueError):
        _exec_require_capability(c, {"capability": "screen_record", "mode": "fail"}, "d1")


def test_require_capability_warn_mode_continues():
    c = _Client({})
    out = _exec_require_capability(c, {"capability": "root", "mode": "warn"}, "d1")
    assert out.startswith("WARN")
