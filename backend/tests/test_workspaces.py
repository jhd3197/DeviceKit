"""Workspaces, membership, grants & narrow-only scoping (plan 20, part 4).

Covers the scope_query contract (no context ⇒ unchanged), the highest-wins role fold + device
danger tiers, membership/last-owner guards, the lenient workspace-context resolution, and the
born-in-workspace automation scoping end to end.
"""
import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.workspaces import WorkspacesMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.mixins.automation import AutomationMixin
from devicekit.services.gate import authorize
from devicekit.services import workspace as wsvc
from devicekit.services.principal import Principal
from devicekit.routes import workspaces as ws_routes, automations as automations_routes


class _WsClient(WorkspacesMixin, AutomationMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _WsClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- scope_query + fold
def test_role_fold_highest_wins():
    assert wsvc.highest(["viewer", "admin", "member"]) == "admin"
    assert wsvc.highest([]) is None
    assert wsvc.role_satisfies("owner", "admin")
    assert not wsvc.role_satisfies("member", "admin")


def test_resolve_workspace_id_lenient():
    class Req:
        headers = {"X-Workspace-Id": " ws1 "}
        args = {}
    assert wsvc.resolve_workspace_id(Req()) == "ws1"

    class Empty:
        headers = {}
        args = {}
    assert wsvc.resolve_workspace_id(Empty()) is None


def test_scope_query_is_opt_in(client):
    # Two automations, one global (no workspace), one in ws1.
    client.create_automation("global-one")
    ws = client.create_workspace("Team", created_by=None)
    client.create_automation("ws-one", workspace_id=ws["id"])
    # No context → unchanged (both visible).
    assert len(client.list_automations()) == 2
    # With context → narrowed to that workspace.
    scoped = client.list_automations(workspace_id=ws["id"])
    assert [a["name"] for a in scoped] == ["ws-one"]


# --------------------------------------------------------------- membership
def test_membership_and_last_owner_guard(client):
    u_owner = client.create_user("owner", "pw123456", role="operator")
    u_two = client.create_user("two", "pw123456", role="operator")
    ws = client.create_workspace("Team", created_by=u_owner["id"])
    # Creator is owner.
    assert client.member_role(u_owner["id"], ws["id"]) == "owner"
    # Cannot demote/remove the only owner.
    with pytest.raises(ValueError):
        client.update_member(ws["id"], u_owner["id"], "member")
    with pytest.raises(ValueError):
        client.remove_member(ws["id"], u_owner["id"])
    # Add a second owner → guard lifts.
    client.add_member(ws["id"], u_two["id"], role="owner")
    assert client.update_member(ws["id"], u_owner["id"], "member")["role"] == "member"


def test_device_action_tiers(client):
    # Workspace with no auto-owner, then add a plain member.
    ws = client.create_workspace("T", created_by=None)
    u2 = client.create_user("m", "pw123456", role="operator")
    client.add_member(ws["id"], u2["id"], role="member")
    member = Principal(kind="user", user_id=u2["id"], role="operator")
    assert client.can_device_action(member, ws["id"], "run_automation")   # member tier
    assert not client.can_device_action(member, ws["id"], "factory_reset")  # admin tier
    # Fleet-wide / raw shell are platform-admin only, never a workspace role.
    assert not client.can_device_action(member, ws["id"], "raw_shell")
    admin = Principal(kind="solo", full_access=True)
    assert client.can_device_action(admin, ws["id"], "raw_shell")


def test_require_member_missing_vs_insufficient(client):
    u = client.create_user("u", "pw123456", role="operator")
    ws = client.create_workspace("T", created_by=u["id"])
    stranger = Principal(kind="user", user_id="nobody", role="operator")
    ok, err = client.require_member(stranger, ws["id"], "viewer")
    assert not ok and err[1] == 404   # missing membership → don't leak existence
    client.add_member(ws["id"], "nobody", role="viewer")
    ok, err = client.require_member(stranger, ws["id"], "admin")
    assert not ok and err[1] == 403   # insufficient role
    admin = Principal(kind="solo", full_access=True)
    assert client.require_member(admin, ws["id"], "owner")[0]  # platform admin bypasses


# --------------------------------------------------------------- grants
def test_grants_visibility(client):
    u = client.create_user("u", "pw123456")
    g1 = client.create_grant("automation", "auto-1", u["id"], level="editor",
                             granted_by="admin")
    assert g1["level"] == "editor"
    assert client.grant_level(u["id"], "automation", "auto-1") == "editor"
    # Idempotent upsert on the same (type,id,user).
    g2 = client.create_grant("automation", "auto-1", u["id"], level="viewer")
    assert g2["id"] == g1["id"] and g2["level"] == "viewer"
    assert client.revoke_grant(g1["id"]) is True
    assert client.grant_level(u["id"], "automation", "auto-1") is None


# --------------------------------------------------------------- HTTP: context + scoping
def test_workspace_context_scopes_automations_over_http(client):
    # Build an app with the real gate + automations blueprint.
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(ws_routes.make_blueprint(client, limiter))
    app.register_blueprint(automations_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc = app.test_client()
    # Solo mode (no users) → admin principal. Create a workspace + an automation in it.
    ws = tc.post("/workspaces", json={"name": "Alpha"}).get_json()["workspace"]
    tc.post("/automations", json={"name": "global-a"})   # no workspace header → global
    tc.post("/automations", json={"name": "scoped-a"},
            headers={"X-Workspace-Id": ws["id"]})
    # No header → all automations.
    assert tc.get("/automations").get_json()["count"] == 2
    # With header → only the workspace's automation.
    scoped = tc.get("/automations", headers={"X-Workspace-Id": ws["id"]}).get_json()
    assert scoped["count"] == 1 and scoped["automations"][0]["name"] == "scoped-a"
    # Unknown workspace header degrades to no scoping (lenient), not an error.
    assert tc.get("/automations", headers={"X-Workspace-Id": "does-not-exist"}).get_json()["count"] == 2


def test_workspace_membership_over_http(client):
    admin = client.create_user("admin", "pw123456", role="admin")
    owner = client.create_user("owner", "pw123456", role="operator")
    member = client.create_user("member", "pw123456", role="viewer")

    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(ws_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc = app.test_client()

    def hdr(u):
        tok = client.create_session(u["id"])
        return {"X-Session-Token": tok}

    # A global operator creates a workspace and becomes its owner.
    ws = tc.post("/workspaces", headers=hdr(owner), json={"name": "Beta"}).get_json()["workspace"]
    # Owner (a global operator!) can add a member — capability fold, not the global matrix.
    r = tc.post(f"/workspaces/{ws['id']}/members", headers=hdr(owner),
                json={"user_id": member["id"], "role": "viewer"})
    assert r.status_code == 201
    # A non-member stranger gets 404 (existence not leaked).
    stranger = client.create_user("stranger", "pw123456", role="operator")
    assert tc.get(f"/workspaces/{ws['id']}/members", headers=hdr(stranger)).status_code == 404
    # The member (global viewer) can list members but not add one.
    assert tc.get(f"/workspaces/{ws['id']}/members", headers=hdr(member)).status_code == 200
    assert tc.post(f"/workspaces/{ws['id']}/members", headers=hdr(member),
                   json={"user_id": "x"}).status_code == 403
    # Platform admin sees every workspace.
    assert tc.get("/workspaces", headers=hdr(admin)).get_json()["count"] == 1
