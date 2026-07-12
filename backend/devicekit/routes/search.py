"""Entity omnisearch route (plan 26, part 3) — ``GET /search?q=``.

One authz-scoped endpoint the command palette hits (debounced, min 2 chars) instead of
pre-fetching whole tables on open. Scopes to the caller's active workspace and role: the
principal's ``workspace_id`` narrows born-in-workspace entities and ``is_admin`` unlocks the
users/workspaces sources. Mirrored under ``/api/v1`` like every other blueprint.
"""
import logging

from flask import Blueprint, jsonify, request, g

from devicekit.services.scopes import require_scope

logger = logging.getLogger(__name__)


def _workspace_id():
    """Active workspace the gate attached to the principal (plan 20 part 4), or None."""
    return getattr(getattr(g, "principal", None), "workspace_id", None)


def _is_admin():
    return bool(getattr(getattr(g, "principal", None), "is_admin", False))


def make_blueprint(client, limiter):
    bp = Blueprint("search", __name__)

    @bp.route("/search")
    @require_scope("devices:read")
    def search():
        """Cross-entity omnisearch. Returns ``{results: [{type, label, sublabel, path}], count}``."""
        term = request.args.get("q", "").strip()
        if len(term) < 2:
            return jsonify({"results": [], "count": 0})
        try:
            results = client.search(term, workspace_id=_workspace_id(), is_admin=_is_admin())
            return jsonify({"results": results, "count": len(results)})
        except Exception as e:
            logger.error(f"Search error: {e}")
            return jsonify({"error": str(e)}), 500

    return bp
