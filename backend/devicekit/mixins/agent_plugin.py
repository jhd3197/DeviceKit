"""AgentPluginMixin — the agent-plugin manifest contract (plan 25 part 5, schema only).

DeviceKit can **declare**, validate, store, and dependency-order agent plugins. It cannot yet
run one: ServerKit's own on-device plugin runtime is a stub, and sandboxed code-on-agent is
genuine greenfield in both projects. So this mixin ships the *contract* — the manifest schema
(capabilities + typed permissions + resource limits + dependency graph) — and
``install_agent_plugin`` is an honest stub that refuses with a clear "runtime not implemented"
rather than pretending. When the runtime lands, these declarations are what it consumes.
"""
import time
import uuid
import logging

from devicekit.db import session_scope
from devicekit.models import AgentPlugin
from devicekit.agent_plugin.manifest import validate_plugin_manifest, AgentPluginError
from devicekit.agent_plugin.graph import resolve_order, DependencyError

logger = logging.getLogger(__name__)


class AgentPluginMixin:
    """Declare + validate agent-plugin manifests; resolve their dependency order.
    On-device execution is deferred (see ``install_agent_plugin``)."""

    def validate_agent_plugin_manifest(self, manifest):
        """Dry validation for editors — never persists. Returns
        ``{valid, errors, normalized?}``."""
        try:
            normalized = validate_plugin_manifest(manifest)
        except AgentPluginError as e:
            return {"valid": False, "errors": e.errors}
        return {"valid": True, "errors": [], "normalized": normalized}

    def declare_agent_plugin(self, manifest, workspace_id=None):
        """Validate + persist a plugin declaration (upsert by name). Raises
        ``AgentPluginError`` on an invalid manifest."""
        normalized = validate_plugin_manifest(manifest)
        now = time.time()
        with session_scope() as s:
            row = (s.query(AgentPlugin)
                   .filter(AgentPlugin.name == normalized["name"]).first())
            if row is None:
                row = AgentPlugin(id=str(uuid.uuid4()), name=normalized["name"],
                                  created_at=now, workspace_id=workspace_id)
                s.add(row)
            row.version = normalized["version"]
            row.manifest = normalized
            row.updated_at = now
            s.flush()
            out = row.to_dict()
        self._broadcast_plugin("declared", out)
        return out

    def list_agent_plugins(self):
        with session_scope() as s:
            return [p.to_dict() for p in
                    s.query(AgentPlugin).order_by(AgentPlugin.name.asc()).all()]

    def get_agent_plugin(self, plugin_id):
        with session_scope() as s:
            p = s.get(AgentPlugin, plugin_id)
            if p is None:
                p = s.query(AgentPlugin).filter(AgentPlugin.name == plugin_id).first()
            return p.to_dict() if p else None

    def delete_agent_plugin(self, plugin_id):
        with session_scope() as s:
            p = s.get(AgentPlugin, plugin_id)
            if p is None:
                p = s.query(AgentPlugin).filter(AgentPlugin.name == plugin_id).first()
            if not p:
                return False
            out = p.to_dict()
            s.delete(p)
        self._broadcast_plugin("deleted", out)
        return True

    def resolve_agent_plugin_order(self):
        """Topological install order over all declared plugins. Returns
        ``{order}`` or ``{error}`` (a cycle or a dependency on an undeclared plugin)."""
        manifests = [p["manifest"] for p in self.list_agent_plugins()]
        try:
            return {"order": resolve_order(manifests)}
        except DependencyError as e:
            return {"error": str(e)}

    def install_agent_plugin(self, plugin_id):
        """Deferred: the on-device plugin runtime does not exist yet (schema-only phase).

        Mirrors ServerKit's ``agent_plugin_service.install_plugin`` stub — an honest refusal,
        not a silent no-op, so callers never believe code shipped to a device.
        """
        plugin = self.get_agent_plugin(plugin_id)
        if not plugin:
            return {"installed": False, "error": "plugin not declared"}
        return {
            "installed": False,
            "plugin": plugin["name"],
            "error": "on-device plugin runtime not implemented — this phase ships the "
                     "manifest contract only (plan 25 part 5); execution is greenfield",
        }

    def _broadcast_plugin(self, event, plugin_dict):
        try:
            self.broadcast("agent_plugin", {"event": event, "plugin": plugin_dict})
        except Exception:
            pass
