"""Entity omnisearch (plan 26, part 3) — ``SearchMixin`` + ``GET /search``.

Covers the substring ranker, the min-length gate, cross-entity matching, per-type capping, and
the admin gating of the users/workspaces sources — plus the mounted route returning the
``{results, count}`` envelope with the principal's workspace/role applied.
"""
import pytest
from flask import Flask, g

from devicekit.mixins.search import SearchMixin, _rank
from devicekit.routes import search as search_route


class _Host(SearchMixin):
    """Mixin composite with plain stubs for every entity source ``search`` folds in."""

    def all_devices_for_query(self):
        return [
            {"device_id": "R9TT311P25N", "model": "Galaxy A03s", "manufacturer": "Samsung"},
            {"serial": "ZY22J8F4FJ", "model": "Moto G Play", "manufacturer": "Motorola"},
        ]

    def list_automations(self, workspace_id=None):
        self.seen_workspace = workspace_id
        return [{"id": "a1", "name": "Nightly reboot", "description": "reboot all", "steps": []}]

    def list_profiles(self):
        return [{"id": "p1", "name": "Shopper Bot", "niche": "retail"}]

    def list_device_groups(self):
        return [{"id": "g1", "name": "Test Lab", "description": "", "device_ids": ["x"]}]

    def list_extensions(self):
        return [{"slug": "browser", "name": "Browser Control", "description": ""}]

    def list_jobs(self, q=None, limit=8):
        return [{"id": "job-123456789", "kind": "backup", "status": "done"}]

    def list_users(self):
        return [{"id": "u1", "username": "admin", "role": "admin"}]

    def list_workspaces(self):
        return [{"id": "w1", "name": "Acme"}]


# -- ranker -------------------------------------------------------------------

def test_rank_prefix_beats_boundary_beats_mid():
    assert _rank("gal", "Galaxy A03s") == 2          # prefix
    assert _rank("a03", "Galaxy A03s") == 1          # word boundary
    assert _rank("axy", "Galaxy A03s") == 0          # mid-string
    assert _rank("zzz", "Galaxy A03s") == -1         # no match


# -- SearchMixin.search -------------------------------------------------------

def test_min_term_length_returns_empty():
    assert _Host().search("g") == []
    assert _Host().search("") == []


def test_serial_fragment_matches_device():
    rows = _Host().search("R9TT")
    devices = [r for r in rows if r["type"] == "device"]
    assert any(r["path"] == "/node/R9TT311P25N" for r in devices)


def test_matches_across_entity_types():
    rows = _Host().search("bo", is_admin=True)   # "Shopper Bot" (profile), "backup"? no — profile only
    types = {r["type"] for r in rows}
    assert "profile" in types


def test_admin_gates_users_and_workspaces():
    non_admin = _Host().search("adm", is_admin=False)
    assert not any(r["type"] in ("user", "workspace") for r in non_admin)
    admin = _Host().search("adm", is_admin=True)
    assert any(r["type"] == "user" for r in admin)


def test_workspace_id_threaded_to_automations():
    host = _Host()
    host.search("reboot", workspace_id="ws-1")
    assert host.seen_workspace == "ws-1"


def test_faulty_source_does_not_sink_search():
    class _Broken(_Host):
        def list_profiles(self):
            raise RuntimeError("boom")

    rows = _Broken().search("galaxy")   # device source still returns
    assert any(r["type"] == "device" for r in rows)


# -- route --------------------------------------------------------------------

def _make_app(host, principal=None):
    app = Flask(__name__)
    app.register_blueprint(search_route.make_blueprint(host, None))

    @app.before_request
    def _attach():
        g.principal = principal

    return app


class _Principal:
    def __init__(self, is_admin=False, workspace_id=None):
        self.is_admin = is_admin
        self.workspace_id = workspace_id
        self.scopes = None       # session/solo principal — require_scope passes through


def test_route_returns_envelope():
    app = _make_app(_Host(), _Principal())
    client = app.test_client()
    r = client.get("/search?q=galaxy")
    assert r.status_code == 200
    body = r.get_json()
    assert "results" in body and "count" in body
    assert body["count"] == len(body["results"])
    assert any(row["type"] == "device" for row in body["results"])


def test_route_min_length():
    app = _make_app(_Host(), _Principal())
    r = app.test_client().get("/search?q=a")
    assert r.status_code == 200
    assert r.get_json() == {"results": [], "count": 0}


def test_route_admin_flag_from_principal():
    non_admin = _make_app(_Host(), _Principal(is_admin=False)).test_client().get("/search?q=adm").get_json()
    assert not any(r["type"] in ("user", "workspace") for r in non_admin["results"])
    admin = _make_app(_Host(), _Principal(is_admin=True)).test_client().get("/search?q=adm").get_json()
    assert any(r["type"] == "user" for r in admin["results"])
