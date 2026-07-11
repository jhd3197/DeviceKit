"""User-attributed audit service (plan 20, part 3).

Covers redaction, proxy-aware IP extraction, the durable ``record_audit`` + query path, and the
folded request-level audit that attributes rows to the resolved principal.
"""
import time

import pytest
from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from devicekit.mixins.audit import AuditMixin
from devicekit.mixins.activity import ActivityMixin
from devicekit.mixins.identity import IdentityMixin
from devicekit.mixins.auth import AuthMixin
from devicekit.services.audit import redact, client_ip
from devicekit.services.gate import authorize
from devicekit.services.principal import Principal
from devicekit.routes import audit as audit_routes


class _AuditClient(AuditMixin, ActivityMixin, IdentityMixin, AuthMixin):
    def __init__(self, api_key=""):
        self.configure_auth(api_key, [])
        self._has_users_flag = None
        self._activities = []


@pytest.fixture
def client(fresh_db, monkeypatch):
    monkeypatch.delenv("DEVICEKIT_ADMIN_USERNAME", raising=False)
    c = _AuditClient()
    c.init_identity()
    return c


# --------------------------------------------------------------- pure helpers
def test_redaction_masks_sensitive_keys():
    out = redact({
        "username": "alice",
        "password": "hunter2",
        "nested": {"api_key": "dk_abc", "count": 3},
        "list": [{"token": "t"}, {"ok": 1}],
    })
    assert out["username"] == "alice"
    assert out["password"] == "***"
    assert out["nested"]["api_key"] == "***" and out["nested"]["count"] == 3
    assert out["list"][0]["token"] == "***" and out["list"][1]["ok"] == 1


def test_client_ip_prefers_forwarded():
    class Req:
        headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
        remote_addr = "10.0.0.1"
    assert client_ip(Req()) == "203.0.113.9"

    class Req2:
        headers = {}
        remote_addr = "127.0.0.1"
    assert client_ip(Req2()) == "127.0.0.1"


# --------------------------------------------------------------- durable record + query
def test_record_and_query(client):
    client.record_audit("device.reboot", user_id="u1", username="alice",
                        target_type="device", target_id="d1",
                        details={"password": "x", "note": "ok"})
    client.record_audit("device.reboot", user_id="u2", username="bob", target_id="d2")
    logs = client.get_audit_logs()
    assert len(logs) == 2
    # details were redacted at rest
    row = client.get_audit_logs(user_id="u1")[0]
    assert row["details"]["password"] == "***" and row["details"]["note"] == "ok"
    assert row["username"] == "alice" and row["target_id"] == "d1"
    # action filter
    assert len(client.get_audit_logs(action="reboot")) == 2
    assert client.get_audit_logs(user_id="u2")[0]["username"] == "bob"


def test_purge_retention(client):
    old = client.record_audit("x")
    # Backdate one row by rewriting created_at directly.
    from devicekit.db import session_scope
    from devicekit.models.audit_log import AuditLog
    with session_scope() as s:
        s.get(AuditLog, old["id"]).created_at = time.time() - 100 * 86400
    client.record_audit("y")
    assert client.purge_audit(retention_days=90) == 1
    assert len(client.get_audit_logs()) == 1


# --------------------------------------------------------------- folded request audit
def test_audit_request_attributes_principal(client):
    app = Flask(__name__)

    @app.before_request
    def _gate():
        g.principal = Principal(kind="user", user_id="u9", username="carol", role="operator",
                                permissions={"automations": {"read": True, "write": True}})
        return None

    @app.after_request
    def _audit(resp):
        client.audit_request(request, resp, getattr(g, "principal", None))
        return resp

    @app.route("/automations", methods=["POST"])
    def _mk():
        return jsonify({"ok": True})

    app.test_client().post("/automations", json={"secret": "s", "name": "n"})
    logs = client.get_audit_logs()
    assert len(logs) == 1
    row = logs[0]
    assert row["action"] == "POST /automations" and row["username"] == "carol"
    assert row["user_id"] == "u9" and row["principal_kind"] == "user" and row["status"] == 200
    # In-memory activity feed also attributed.
    assert client.get_activities()[0]["user_id"] == "u9"


def test_audit_skips_reads_and_5xx(client):
    app = Flask(__name__)

    @app.after_request
    def _audit(resp):
        client.audit_request(request, resp, None)
        return resp

    @app.route("/thing")
    def _get():
        return jsonify({"ok": True})

    @app.route("/boom", methods=["POST"])
    def _boom():
        return jsonify({"error": "x"}), 500

    tc = app.test_client()
    tc.get("/thing")
    tc.post("/boom")
    assert client.get_audit_logs() == []  # GET not audited, 500 not audited


# --------------------------------------------------------------- HTTP route (admin-only)
def test_audit_route_admin_only(client):
    client.record_audit("seed")
    app = Flask(__name__)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
    app.register_blueprint(audit_routes.make_blueprint(client, limiter))

    @app.before_request
    def _gate():
        principal, error = authorize(client, request)
        g.principal = principal
        if error:
            body, status = error
            return jsonify(body), status
        return None

    tc = app.test_client()
    # Solo mode (no users) → admin principal → allowed.
    r = tc.get("/audit")
    assert r.status_code == 200 and r.get_json()["count"] == 1

    # With a viewer principal, forbidden.
    client.create_user("v", "pw123456", role="viewer")
    tok = client.create_session(client.get_user(client.list_users()[0]["id"])["id"])

    class _R:
        headers = {"X-Session-Token": tok}
        args, cookies = {}, {}
    # Direct principal check (viewer can't read audit).
    p = client.resolve_principal(_R())
    assert p.kind == "user" and not p.is_admin
