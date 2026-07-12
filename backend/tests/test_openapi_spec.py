"""Plan 21 phase 2 — the auto-generated OpenAPI spec over the /api/v1 mirror.

The generator walks the live ``url_map``; these tests mount a small but real subset of
blueprints (bare + v1 mirror, exactly as ``register_all`` does) and assert the document
stays in sync with the routes — no hand-maintained spec to drift.
"""
import pytest
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.routes import api_v1, automations, device_control, health
from devicekit.services.openapi import generate_openapi


class _Host:
    """Duck-typed client: make_blueprint only closes over it, nothing runs at mount time."""


@pytest.fixture
def app():
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    host = _Host()
    for module in (api_v1, health, device_control, automations):
        app.register_blueprint(module.make_blueprint(host, limiter))
        if module is not api_v1:
            bp = module.make_blueprint(host, limiter)
            app.register_blueprint(bp, url_prefix="/api/v1", name=f"v1_{bp.name}")
    return app


@pytest.fixture
def spec(app):
    return generate_openapi(app)


def test_spec_skeleton(spec):
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] == "DeviceKit Public API"
    assert spec["info"]["version"] == "v1"
    schemes = spec["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert {"ApiKeyAuth": []} in spec["security"]


def test_only_versioned_paths_documented(spec):
    paths = spec["paths"]
    assert paths, "spec documented no paths"
    for path in paths:
        assert path.startswith("/api/v1"), f"bare-mount path leaked into the spec: {path}"
    # The bare mirror of the same rules must not appear.
    assert "/devices/{device_id}/tap" not in paths
    assert "/api/v1/devices/{device_id}/tap" in paths


def test_path_params_converted(spec):
    op = spec["paths"]["/api/v1/devices/{device_id}/tap"]["post"]
    params = {p["name"] for p in op["parameters"]}
    assert params == {"device_id"}
    assert all(p["in"] == "path" and p["required"] for p in op["parameters"])


def test_tags_come_from_blueprints(spec):
    tag_names = {t["name"] for t in spec["tags"]}
    assert {"device_control", "automations", "health", "meta"} <= tag_names
    assert spec["paths"]["/api/v1/devices/{device_id}/tap"]["post"]["tags"] == ["device_control"]


def test_required_scope_advertised(spec):
    """require_scope stamps flow through wrapper chains into x-required-scope."""
    tap = spec["paths"]["/api/v1/devices/{device_id}/tap"]["post"]
    assert tap["x-required-scope"] == "devices:command"
    assert "devices:command" in tap.get("description", "")
    run = spec["paths"]["/api/v1/automations/{automation_id}/run"]["post"]
    assert run["x-required-scope"] == "automations:run"


def test_public_paths_marked(spec):
    health_op = spec["paths"]["/api/v1/health"]["get"]
    assert health_op["security"] == []
    assert "401" not in health_op["responses"]
    gated = spec["paths"]["/api/v1/devices/{device_id}/tap"]["post"]
    assert "401" in gated["responses"] and "403" in gated["responses"]


def test_docstrings_become_summaries(app, spec):
    meta_op = spec["paths"]["/api/v1"]["get"]
    assert meta_op["summary"].startswith("Public API discovery")


def test_spec_route_served(app):
    """The /api/v1/openapi.json + /api/v1/docs endpoints render from the live app."""
    client = app.test_client()
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    assert res.get_json()["info"]["version"] == "v1"
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert b"DeviceKit API" in docs.data
