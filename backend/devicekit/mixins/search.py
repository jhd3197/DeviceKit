"""Entity omnisearch (plan 26, part 3) — one authz-scoped ``/search`` across the fleet.

The command palette used to fetch whole tables on open (``/devices`` + ``/automations``) and
filter them client-side. That stops scaling past a few dozen devices. ``SearchMixin.search`` folds
every searchable entity into one call that returns lightweight rows ``{type, label, sublabel,
path}`` the palette maps straight to categories — devices, automations, profiles, fleet groups,
extensions, recent jobs, and (admins only) users/workspaces.

Scoping mirrors the rest of the app: automations narrow to the active workspace via the shared
``scope_query`` path (already applied by ``list_automations``), and the user/workspace sources are
gated to admins by the caller (the route passes ``is_admin`` from the principal). Each source is
defensive — a mixin that isn't composed, or a source that raises, is skipped rather than failing
the whole search.
"""
import logging

logger = logging.getLogger(__name__)

# Per-type cap so one noisy entity can't crowd the palette; the frontend applies its own
# per-group cap on top. Kept modest — the palette shows a handful per category.
DEFAULT_PER_TYPE = 8
MIN_TERM_LEN = 2


def _rank(term, *fields):
    """Substring relevance for a row: -1 no match, 0 mid-string, 1 word-boundary, 2 prefix.

    ``term`` is already lowercased. Higher is a better match; the caller sorts desc so a serial
    fragment that *starts* a device id beats one buried mid-string."""
    best = -1
    for f in fields:
        if not f:
            continue
        s = str(f).lower()
        idx = s.find(term)
        if idx < 0:
            continue
        if idx == 0:
            best = max(best, 2)
        elif not s[idx - 1].isalnum():
            best = max(best, 1)
        else:
            best = max(best, 0)
    return best


class SearchMixin:
    """Cross-entity omnisearch backing ``GET /search``."""

    def search(self, term, workspace_id=None, is_admin=False, per_type=DEFAULT_PER_TYPE):
        """Return ranked ``{type, label, sublabel, path}`` rows across every entity.

        ``term`` shorter than 2 chars returns nothing (the palette also min-gates). ``workspace_id``
        narrows the born-in-workspace entities; ``is_admin`` unlocks the users/workspaces sources.
        """
        term = (term or "").strip().lower()
        if len(term) < MIN_TERM_LEN:
            return []

        rows = []
        rows += self._search_devices(term, per_type)
        rows += self._search_automations(term, per_type, workspace_id)
        rows += self._search_profiles(term, per_type)
        rows += self._search_groups(term, per_type)
        rows += self._search_extensions(term, per_type)
        rows += self._search_jobs(term, per_type)
        if is_admin:
            rows += self._search_users(term, per_type)
            rows += self._search_workspaces(term, per_type)
        return rows

    # -- per-entity sources ---------------------------------------------------
    # Each returns a list of rows, ranked and capped, and swallows its own errors so a single
    # missing/faulty source never sinks the whole search.

    def _ranked(self, candidates, per_type):
        """Sort ``(rank, row)`` tuples by rank desc, drop non-matches, cap, return rows."""
        hits = [(r, row) for r, row in candidates if r >= 0]
        hits.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in hits[:per_type]]

    def _search_devices(self, term, per_type):
        try:
            devices = (self.all_devices_for_query()
                       if hasattr(self, "all_devices_for_query") else [])
            out = []
            for d in devices:
                did = d.get("device_id") or d.get("serial")
                if not did:
                    continue
                model = d.get("model") or d.get("name") or ""
                manuf = d.get("manufacturer") or ""
                rank = _rank(term, did, model, manuf)
                out.append((rank, {
                    "type": "device",
                    "label": model or did,
                    "sublabel": did,
                    "path": f"/node/{did}",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: devices source skipped: {e}")
            return []

    def _search_automations(self, term, per_type, workspace_id):
        try:
            items = (self.list_automations(workspace_id=workspace_id)
                     if hasattr(self, "list_automations") else [])
            out = []
            for a in items:
                if not a.get("id"):
                    continue
                name = a.get("name") or "Untitled automation"
                desc = a.get("description") or ""
                rank = _rank(term, name, desc)
                out.append((rank, {
                    "type": "automation",
                    "label": name,
                    "sublabel": desc or f"{len(a.get('steps') or [])} steps",
                    "path": f"/automations/{a['id']}/edit",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: automations source skipped: {e}")
            return []

    def _search_profiles(self, term, per_type):
        try:
            items = self.list_profiles() if hasattr(self, "list_profiles") else []
            out = []
            for p in items:
                if not p.get("id"):
                    continue
                name = p.get("name") or "Untitled profile"
                niche = p.get("niche") or p.get("model_name") or ""
                rank = _rank(term, name, niche, p.get("personality") or "")
                out.append((rank, {
                    "type": "profile",
                    "label": name,
                    "sublabel": niche,
                    "path": f"/profiles/{p['id']}/edit",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: profiles source skipped: {e}")
            return []

    def _search_groups(self, term, per_type):
        try:
            items = self.list_device_groups() if hasattr(self, "list_device_groups") else []
            out = []
            for g in items:
                if not g.get("id"):
                    continue
                name = g.get("name") or "Untitled group"
                desc = g.get("description") or ""
                rank = _rank(term, name, desc)
                n = len(g.get("device_ids") or [])
                out.append((rank, {
                    "type": "group",
                    "label": name,
                    "sublabel": desc or f"{n} devices",
                    "path": "/fleet/groups",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: groups source skipped: {e}")
            return []

    def _search_extensions(self, term, per_type):
        try:
            items = self.list_extensions() if hasattr(self, "list_extensions") else []
            out = []
            for x in items:
                slug = x.get("slug") or x.get("id")
                name = x.get("name") or slug or ""
                if not name:
                    continue
                rank = _rank(term, name, slug, x.get("description") or "")
                out.append((rank, {
                    "type": "extension",
                    "label": name,
                    "sublabel": slug or "",
                    "path": "/extensions",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: extensions source skipped: {e}")
            return []

    def _search_jobs(self, term, per_type):
        try:
            if not hasattr(self, "list_jobs"):
                return []
            # The job service already substring-filters via ``q``; fetch a small recent slice.
            items = self.list_jobs(q=term, limit=per_type)
            out = []
            for j in items:
                jid = j.get("id")
                if not jid:
                    continue
                kind = j.get("kind") or "job"
                status = j.get("status") or ""
                # Already filtered server-side by ``q`` — emit rows directly (no re-ranking).
                out.append({
                    "type": "job",
                    "label": kind,
                    "sublabel": f"{status} · {str(jid)[:8]}",
                    "path": "/jobs",
                })
            return out[:per_type]
        except Exception as e:
            logger.debug(f"search: jobs source skipped: {e}")
            return []

    def _search_users(self, term, per_type):
        try:
            items = self.list_users() if hasattr(self, "list_users") else []
            out = []
            for u in items:
                uname = u.get("username") or u.get("id") or ""
                if not uname:
                    continue
                rank = _rank(term, uname, u.get("role") or "")
                out.append((rank, {
                    "type": "user",
                    "label": uname,
                    "sublabel": u.get("role") or "",
                    "path": "/settings/users",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: users source skipped: {e}")
            return []

    def _search_workspaces(self, term, per_type):
        try:
            items = self.list_workspaces() if hasattr(self, "list_workspaces") else []
            out = []
            for w in items:
                name = w.get("name") or w.get("id") or ""
                if not name:
                    continue
                rank = _rank(term, name, w.get("slug") or "")
                out.append((rank, {
                    "type": "workspace",
                    "label": name,
                    "sublabel": "workspace",
                    "path": "/settings/workspaces",
                }))
            return self._ranked(out, per_type)
        except Exception as e:
            logger.debug(f"search: workspaces source skipped: {e}")
            return []
