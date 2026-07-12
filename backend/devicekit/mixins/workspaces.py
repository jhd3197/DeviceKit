"""Workspaces, membership, grants & the capability fold (plan 20, part 4).

Owns workspace/member/grant CRUD, the highest-wins role fold, and the two authorization helpers
the routes call: ``resolve_workspace_context`` (lenient — attaches a workspace to the principal
only when it exists AND the principal may use it) and ``require_member`` (404 missing / 403
insufficient). Device danger tiers map onto the same fold via ``can_device_action``.
"""
import time
import uuid
import logging

from slugify import slugify

from devicekit.db import session_scope
from devicekit.models.workspace import (
    Workspace, WorkspaceMember, ResourceGrant, WORKSPACE_STATUSES,
)
from devicekit.services.workspace import (
    WORKSPACE_ROLES, GRANT_LEVELS, DEVICE_ACTION_TIERS, PLATFORM_ADMIN_ONLY,
    role_rank, role_satisfies, highest, resolve_workspace_id,
)

logger = logging.getLogger(__name__)


class WorkspacesMixin:
    """Tenancy: workspaces, membership, resource grants, and the capability fold."""

    # -----------------------------------------------------------------
    # Workspace CRUD
    # -----------------------------------------------------------------
    def create_workspace(self, name, slug=None, created_by=None, max_devices=None,
                         max_members=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        slug = slugify(slug or name)
        if not slug:
            raise ValueError("could not derive a slug")
        with session_scope() as s:
            if s.query(Workspace).filter(Workspace.slug == slug).first():
                raise ValueError(f"workspace slug already exists: {slug}")
            ws = Workspace(id=str(uuid.uuid4()), name=name, slug=slug, status="active",
                           max_devices=max_devices, max_members=max_members,
                           created_by=created_by, created_at=time.time())
            s.add(ws)
            s.flush()
            # The creator becomes owner (when there is a real user behind the request).
            if created_by:
                s.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=ws.id,
                                      user_id=created_by, role="owner", created_at=time.time()))
            return ws.to_dict()

    def list_workspaces(self, for_user=None):
        """All workspaces, or (when ``for_user`` is set) only those the user is a member of."""
        with session_scope() as s:
            if for_user is None:
                rows = s.query(Workspace).order_by(Workspace.created_at.asc()).all()
                return [w.to_dict() for w in rows]
            member_ids = [m.workspace_id for m in
                          s.query(WorkspaceMember).filter(WorkspaceMember.user_id == for_user).all()]
            if not member_ids:
                return []
            rows = s.query(Workspace).filter(Workspace.id.in_(member_ids)).all()
            return [w.to_dict() for w in rows]

    def get_workspace(self, workspace_id):
        with session_scope() as s:
            ws = s.get(Workspace, workspace_id)
            return ws.to_dict() if ws else None

    def update_workspace(self, workspace_id, name=None, status=None, max_devices=None,
                        max_members=None):
        with session_scope() as s:
            ws = s.get(Workspace, workspace_id)
            if not ws:
                raise ValueError("workspace not found")
            if name is not None:
                ws.name = name.strip() or ws.name
            if status is not None:
                if status not in WORKSPACE_STATUSES:
                    raise ValueError(f"unknown status: {status}")
                ws.status = status
            if max_devices is not None:
                ws.max_devices = max_devices
            if max_members is not None:
                ws.max_members = max_members
            ws.updated_at = time.time()
            return ws.to_dict()

    def delete_workspace(self, workspace_id):
        with session_scope() as s:
            ws = s.get(Workspace, workspace_id)
            if not ws:
                raise ValueError("workspace not found")
            s.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).delete()
            s.delete(ws)
        return True

    # -----------------------------------------------------------------
    # Membership
    # -----------------------------------------------------------------
    def add_member(self, workspace_id, user_id, role="member"):
        if role not in WORKSPACE_ROLES:
            raise ValueError(f"unknown role: {role}")
        with session_scope() as s:
            if not s.get(Workspace, workspace_id):
                raise ValueError("workspace not found")
            existing = s.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id).first()
            if existing:
                existing.role = role
                return existing.to_dict()
            m = WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace_id,
                                user_id=user_id, role=role, created_at=time.time())
            s.add(m)
            s.flush()
            return m.to_dict()

    def update_member(self, workspace_id, user_id, role):
        if role not in WORKSPACE_ROLES:
            raise ValueError(f"unknown role: {role}")
        with session_scope() as s:
            m = s.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id).first()
            if not m:
                raise ValueError("member not found")
            # Last-owner guard: never demote the final owner.
            if m.role == "owner" and role != "owner" and self._owner_count(s, workspace_id) <= 1:
                raise ValueError("cannot demote the last owner")
            m.role = role
            return m.to_dict()

    def remove_member(self, workspace_id, user_id):
        with session_scope() as s:
            m = s.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id).first()
            if not m:
                raise ValueError("member not found")
            if m.role == "owner" and self._owner_count(s, workspace_id) <= 1:
                raise ValueError("cannot remove the last owner")
            s.delete(m)
        return True

    def list_members(self, workspace_id):
        with session_scope() as s:
            rows = s.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id).all()
            return [m.to_dict() for m in rows]

    @staticmethod
    def _owner_count(session, workspace_id):
        return session.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner").count()

    def member_role(self, user_id, workspace_id):
        """The user's direct membership role in a workspace, or ``None``."""
        if not user_id or not workspace_id:
            return None
        with session_scope() as s:
            m = s.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id).first()
            return m.role if m else None

    # -----------------------------------------------------------------
    # Resource grants (visibility only)
    # -----------------------------------------------------------------
    def create_grant(self, resource_type, resource_id, user_id, level="viewer",
                     granted_by=None):
        if resource_type not in ("device", "automation"):
            raise ValueError("resource_type must be device or automation")
        if level not in GRANT_LEVELS:
            raise ValueError(f"unknown grant level: {level}")
        with session_scope() as s:
            existing = s.query(ResourceGrant).filter(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                ResourceGrant.user_id == user_id).first()
            if existing:
                existing.level = level
                return existing.to_dict()
            g = ResourceGrant(id=str(uuid.uuid4()), resource_type=resource_type,
                              resource_id=resource_id, user_id=user_id, level=level,
                              granted_by=granted_by, created_at=time.time())
            s.add(g)
            s.flush()
            return g.to_dict()

    def list_grants(self, resource_type=None, resource_id=None, user_id=None):
        with session_scope() as s:
            q = s.query(ResourceGrant)
            if resource_type:
                q = q.filter(ResourceGrant.resource_type == resource_type)
            if resource_id:
                q = q.filter(ResourceGrant.resource_id == resource_id)
            if user_id:
                q = q.filter(ResourceGrant.user_id == user_id)
            return [g.to_dict() for g in q.all()]

    def revoke_grant(self, grant_id):
        with session_scope() as s:
            g = s.get(ResourceGrant, grant_id)
            if not g:
                raise ValueError("grant not found")
            s.delete(g)
        return True

    def resource_workspace_id(self, resource_type, resource_id):
        """Which workspace a shareable resource belongs to (for grant authorization)."""
        if not resource_type or not resource_id:
            return None
        with session_scope() as s:
            if resource_type == "automation":
                from devicekit.models.automation import Automation
                row = s.get(Automation, resource_id)
                return row.workspace_id if row else None
            if resource_type == "device":
                from devicekit.models.agent_device import AgentDevice
                row = s.get(AgentDevice, resource_id)
                return row.workspace_id if row else None
        return None

    def grant_level(self, user_id, resource_type, resource_id):
        with session_scope() as s:
            g = s.query(ResourceGrant).filter(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                ResourceGrant.user_id == user_id).first()
            return g.level if g else None

    # -----------------------------------------------------------------
    # The capability fold + gate helpers
    # -----------------------------------------------------------------
    def resolve_workspace_context(self, request, principal):
        """Return the workspace id to scope this request by, or ``None``.

        Lenient: an absent header, an unknown workspace, or a principal with no membership all
        degrade to ``None`` (no scoping) rather than an error. A platform admin may use any
        existing workspace."""
        wid = resolve_workspace_id(request)
        if not wid:
            return None
        if not self.get_workspace(wid):
            return None
        if getattr(principal, "is_admin", False):
            return wid
        if self.member_role(getattr(principal, "user_id", None), wid):
            return wid
        return None  # forbidden → degrade

    def require_member(self, principal, workspace_id, min_role="viewer"):
        """Authorize a workspace action. Returns ``(ok, error)`` where error is ``(body, status)``.

        Platform admins bypass. Otherwise: no membership → 404 (don't leak existence); a role below
        ``min_role`` → 403."""
        if getattr(principal, "is_admin", False):
            return True, None
        role = self.member_role(getattr(principal, "user_id", None), workspace_id)
        if not role:
            return False, ({"error": "workspace not found"}, 404)
        if not role_satisfies(role, min_role):
            return False, ({"error": "Insufficient workspace role"}, 403)
        return True, None

    def can_device_action(self, principal, workspace_id, action):
        """Whether the principal may perform a device danger-tier action in a workspace.

        Fleet-wide / raw shell / raw ADB are platform-admin only and can never be unlocked by a
        workspace role. Everything else folds onto the membership tier."""
        if action in PLATFORM_ADMIN_ONLY:
            return bool(getattr(principal, "is_admin", False))
        if getattr(principal, "is_admin", False):
            return True
        min_role = DEVICE_ACTION_TIERS.get(action)
        if min_role is None:
            return False
        role = self.member_role(getattr(principal, "user_id", None), workspace_id)
        return bool(role) and role_satisfies(role, min_role)
