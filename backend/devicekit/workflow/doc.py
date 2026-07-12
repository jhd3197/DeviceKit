"""WorkflowDoc structure: queries, validation, slugs, and the linear→graph shim.

The stored shape is tramo's ``WorkflowDoc`` verbatim (``@tramo/spec`` ``types.ts``):

    {"version": 1,
     "nodes": [{"id", "type", "config", "label"?, "runAfter"?, "retry"?, ...}],
     "edges": [{"id", "source", "target", "sourceHandle"?, "targetHandle"?}],
     "meta":  {"name"?, "revision"?, ...}}

``topo_sort`` mirrors ``@tramo/spec``'s ``topoSort`` (Kahn) so the editor and the
backend agree on validity; ``slugify``/``build_step_slug_map`` mirror ``slug.ts`` so
``{{steps.<slug>.<path>}}`` refs resolve to the same node on both sides.
"""
import re
import unicodedata
import uuid

SPEC_VERSION = 1

#: Node types whose DeviceKit executor is a step-type from the plan-15 registry.
#: The compat shim emits them and the node pack (plan 22 part 2) serves them.
DK_STEP_PREFIX = "dk."

TRIGGER_TYPES = ("manual-trigger", "webhook-trigger", "cron-trigger", "dk.event-trigger")


def is_workflow_doc(value):
    """Cheap structural sniff — enough to route storage/validation, not full validation."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("nodes"), list)
        and isinstance(value.get("edges"), list)
    )


# ---------------------------------------------------------------------------
# Queries (port of @tramo/spec query.ts)
# ---------------------------------------------------------------------------

def find_node(doc, node_id):
    for n in doc.get("nodes", []):
        if n.get("id") == node_id:
            return n
    return None


def incoming_edges(doc, node_id):
    return [e for e in doc.get("edges", []) if e.get("target") == node_id]


def outgoing_edges(doc, node_id):
    return [e for e in doc.get("edges", []) if e.get("source") == node_id]


def get_roots(doc):
    has_incoming = {e.get("target") for e in doc.get("edges", [])}
    return [n for n in doc.get("nodes", []) if n.get("id") not in has_incoming]


def topo_sort(doc):
    """Kahn's algorithm — mirror of ``@tramo/spec`` ``topoSort``.

    Returns ``{"ok": bool, "order": [node ids], "cycle": [...], "error": str}``.
    """
    nodes = doc.get("nodes", [])
    edges = doc.get("edges", [])
    indegree = {n["id"]: 0 for n in nodes if n.get("id")}
    for e in edges:
        target = e.get("target")
        if target in indegree:
            indegree[target] = indegree[target] + 1

    queue = [nid for nid, deg in indegree.items() if deg == 0]
    order = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for e in edges:
            if e.get("source") != nid:
                continue
            target = e.get("target")
            if target not in indegree:
                continue
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(order) != len(indegree):
        cycle = [nid for nid, deg in indegree.items() if deg > 0]
        return {
            "ok": False,
            "order": [],
            "cycle": cycle,
            "error": f"Cycle detected in workflow ({len(cycle)} nodes participating: "
                     f"{', '.join(cycle[:5])}{'…' if len(cycle) > 5 else ''}).",
        }
    return {"ok": True, "order": order, "cycle": [], "error": None}


def validate_doc(doc):
    """Structural + Kahn validation. Returns ``{"ok": bool, "errors": [str], "cycle": []}``.

    The backend authority behind ``POST /automations/<id>/validate``; the editor runs
    the same ``topoSort`` client-side for instant feedback.
    """
    errors = []
    if not isinstance(doc, dict):
        return {"ok": False, "errors": ["Document must be an object"], "cycle": []}
    if doc.get("version") != SPEC_VERSION:
        errors.append(f"Unsupported spec version {doc.get('version')!r} (expected {SPEC_VERSION})")
    nodes = doc.get("nodes")
    edges = doc.get("edges")
    if not isinstance(nodes, list):
        errors.append("'nodes' must be a list")
        nodes = []
    if not isinstance(edges, list):
        errors.append("'edges' must be a list")
        edges = []

    seen_ids = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict) or not n.get("id"):
            errors.append(f"Node #{i} is missing an id")
            continue
        if n["id"] in seen_ids:
            errors.append(f"Duplicate node id '{n['id']}'")
        seen_ids.add(n["id"])
        if not n.get("type"):
            errors.append(f"Node '{n['id']}' is missing a type")
        run_after = n.get("runAfter")
        if run_after not in (None, "on-success", "on-error", "always"):
            errors.append(f"Node '{n['id']}' has invalid runAfter '{run_after}'")
        retry = n.get("retry")
        if retry is not None:
            if not isinstance(retry, dict) or not isinstance(retry.get("count"), (int, float)):
                errors.append(f"Node '{n['id']}' has an invalid retry policy (needs numeric 'count')")

    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errors.append(f"Edge #{i} is not an object")
            continue
        src, tgt = e.get("source"), e.get("target")
        if src not in seen_ids:
            errors.append(f"Edge '{e.get('id', i)}' references unknown source '{src}'")
        if tgt not in seen_ids:
            errors.append(f"Edge '{e.get('id', i)}' references unknown target '{tgt}'")

    cycle = []
    if not errors:
        topo = topo_sort(doc)
        if not topo["ok"]:
            errors.append(topo["error"])
            cycle = topo["cycle"]

    return {"ok": not errors, "errors": errors, "cycle": cycle}


# ---------------------------------------------------------------------------
# Slugs (port of @tramo/spec slug.ts — keep in sync)
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(raw):
    without_templates = _TEMPLATE_RE.sub(" ", raw or "")
    lowered = unicodedata.normalize("NFKD", without_templates.lower())
    stripped = "".join(c for c in lowered if not unicodedata.combining(c))
    return _NON_ALNUM_RE.sub("_", stripped).strip("_")


def node_slug(node):
    source = (node.get("label") or node.get("type") or "").strip()
    return slugify(source) or node.get("id")


def build_step_slug_map(doc):
    """Doc-wide slug↔id maps; collisions suffixed ``_2``, ``_3``… in document order."""
    slug_to_id, id_to_slug, taken = {}, {}, set()
    for node in doc.get("nodes", []):
        base = node_slug(node)
        candidate, n = base, 2
        while candidate in taken:
            candidate = f"{base}_{n}"
            n += 1
        taken.add(candidate)
        slug_to_id[candidate] = node["id"]
        id_to_slug[node["id"]] = candidate
    return slug_to_id, id_to_slug


# ---------------------------------------------------------------------------
# Compat shim — a linear step list rendered as a straight-line WorkflowDoc
# ---------------------------------------------------------------------------

def linear_steps_to_doc(automation):
    """Render an existing linear automation as a straight-line WorkflowDoc
    (``manual-trigger`` → step → step …) so the tramo editor can open it without
    any user migration. Deterministic: node ids reuse the step ids, so re-shimming
    yields the same doc. Steps become ``dk.<type>`` nodes with ``critical: true``
    (preserving the linear engine's abort-on-failure behavior).
    """
    steps = automation.get("steps") or []
    trigger_id = "trigger"
    nodes = [{
        "id": trigger_id,
        "type": "manual-trigger",
        "label": "Manual Trigger",
        "config": {},
    }]
    edges = []
    prev = trigger_id
    for idx, step in enumerate(steps):
        node_id = step.get("id") or f"step_{idx}"
        config = dict(step.get("config") or {})
        config.setdefault("critical", True)
        nodes.append({
            "id": node_id,
            "type": f"{DK_STEP_PREFIX}{step.get('type', 'unknown')}",
            "label": step.get("label") or step.get("type", ""),
            "config": config,
        })
        edges.append({
            "id": f"e_{prev}_{node_id}",
            "source": prev,
            "target": node_id,
        })
        prev = node_id
    return {
        "version": SPEC_VERSION,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "name": automation.get("name", ""),
            "description": automation.get("description", ""),
            "revision": 0,
            "shim": True,   # marks a derived doc; cleared on first real graph save
        },
    }


def new_node_id():
    return f"n_{uuid.uuid4().hex[:10]}"
