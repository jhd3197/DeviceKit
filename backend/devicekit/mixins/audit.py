"""Central user-attributed audit service (plan 20, part 3).

``record_audit`` is the one write path; ``audit_request`` folds the api_app after-request hook
(what used to be a bare ``log_activity``) into it — attributing the durable row to the resolved
principal, extracting a proxy-aware IP/UA, and redacting sensitive keys. The in-memory activity
feed is still fed too, so ``/activities`` is unchanged.
"""
import time
import uuid
import logging

from devicekit.db import session_scope
from devicekit.models.audit_log import AuditLog
from devicekit.services.audit import redact, client_ip, user_agent as _ua

logger = logging.getLogger(__name__)

# Requests worth auditing (state changes only), matching the historical after_request filter.
_AUDIT_METHODS = ("POST", "PUT", "DELETE", "PATCH")


class AuditMixin:
    """Durable, identity-attributed audit trail."""

    def record_audit(self, action, user_id=None, username=None, principal_kind=None,
                     target_type=None, target_id=None, details=None, status=None,
                     ip=None, user_agent=None):
        """Persist one audit row. ``details`` is redacted before it touches the DB."""
        try:
            with session_scope() as s:
                row = AuditLog(
                    id=str(uuid.uuid4()),
                    action=action,
                    user_id=user_id,
                    username=username,
                    principal_kind=principal_kind,
                    target_type=target_type,
                    target_id=target_id,
                    details=redact(details or {}),
                    status=status,
                    ip=ip,
                    user_agent=user_agent,
                    created_at=time.time(),
                )
                s.add(row)
                s.flush()
                return row.to_dict()
        except Exception as e:  # auditing must never break the request it is recording
            logger.warning(f"Audit record failed for {action}: {e}")
            return None

    def audit_request(self, request, response, principal=None):
        """Fold the request-level audit: durable attributed row + in-memory activity feed."""
        if request.method not in _AUDIT_METHODS or response.status_code >= 500:
            return
        user_id = getattr(principal, "user_id", None)
        username = getattr(principal, "username", None)
        kind = getattr(principal, "kind", None)
        ip = client_ip(request)
        self.record_audit(
            action=f"{request.method} {request.path}",
            user_id=user_id,
            username=username,
            principal_kind=kind,
            details={"status": response.status_code},
            status=response.status_code,
            ip=ip,
            user_agent=_ua(request),
        )
        # Keep the historical in-memory activity feed populated (now attributed).
        try:
            self.log_activity(
                action=f"{request.method} {request.path}",
                details={"status": response.status_code},
                source_ip=ip,
                authenticated=bool(principal and getattr(principal, "is_authenticated", False)),
                user_id=user_id,
            )
        except Exception:
            pass

    def get_audit_logs(self, limit=100, user_id=None, action=None,
                       target_type=None, target_id=None, since=None):
        with session_scope() as s:
            q = s.query(AuditLog)
            if user_id:
                q = q.filter(AuditLog.user_id == user_id)
            if action:
                q = q.filter(AuditLog.action.like(f"%{action}%"))
            if target_type:
                q = q.filter(AuditLog.target_type == target_type)
            if target_id:
                q = q.filter(AuditLog.target_id == target_id)
            if since:
                q = q.filter(AuditLog.created_at >= float(since))
            rows = q.order_by(AuditLog.created_at.desc()).limit(min(int(limit), 1000)).all()
            return [r.to_dict() for r in rows]

    def purge_audit(self, retention_days=90):
        """Delete audit rows older than ``retention_days``. Returns the number removed."""
        cutoff = time.time() - float(retention_days) * 86400
        with session_scope() as s:
            return s.query(AuditLog).filter(AuditLog.created_at < cutoff).delete()
