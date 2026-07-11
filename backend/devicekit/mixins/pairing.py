"""RustDesk-style agent enrollment / pairing (plan 07 phase 3).

Flow (ported from ServerKit's ``pairing_service.py``):

1. **enroll** — the on-device agent POSTs its device info and gets back a short, rotating
   6-character ``code`` (ambiguous characters removed) plus a ``pairing_id`` it polls. A
   ``PendingAgent`` row holds the request until claimed or expired.
2. **claim** — an operator types the code into the dashboard (optionally confirming with the
   panel passphrase). The backend mints a per-device HMAC secret, promotes the device into
   ``agent_devices``, and stamps the pending row ``claimed`` with the ``issued_secret``.
3. **poll** — the agent's next poll of ``pairing_id`` receives ``{claimed, device_id,
   secret}`` exactly once; the row is then deleted and the agent switches to signed requests.

Beats the open ``/agent-device/register`` path: an unenrolled agent gets no credentials, so
with ``AGENT_ENROLLMENT_REQUIRED`` on it cannot report at all until an operator claims it.
"""
import time
import secrets
import logging

from devicekit.db import session_scope
from devicekit.models import PendingAgent

logger = logging.getLogger(__name__)

# Unambiguous alphabet (no 0/O/1/I/L) for a code a human reads off a phone screen.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 6
_PAIRING_TTL = 600  # seconds a code stays claimable


class PairingMixin:
    """Enroll → claim → poll pairing flow backed by ``PendingAgent`` rows."""

    @staticmethod
    def _generate_pairing_code():
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))

    def _prune_expired_pending(self):
        now = time.time()
        with session_scope() as s:
            expired = s.query(PendingAgent).filter(
                PendingAgent.expires_at < now, PendingAgent.claimed == False).all()  # noqa: E712
            for row in expired:
                s.delete(row)

    def enroll_agent(self, info, serial=None, ip=None):
        """Start enrollment. Returns ``{pairing_id, code, device_id, expires_at}``."""
        self._prune_expired_pending()
        info = info or {}
        model = info.get("model", "unknown")
        manufacturer = info.get("manufacturer", "unknown")
        device_id = f"{manufacturer}_{model}".replace(" ", "_")
        now = time.time()

        # Fresh, unique code across live pending rows.
        with session_scope() as s:
            for _ in range(10):
                code = self._generate_pairing_code()
                exists = s.query(PendingAgent).filter_by(code=code, claimed=False).first()
                if not exists:
                    break
            row = PendingAgent(
                code=code, device_id=device_id, info=info, serial=serial,
                created_at=now, expires_at=now + _PAIRING_TTL, claimed=False,
                last_ip=ip)
            s.add(row)
            s.flush()
            result = {
                "pairing_id": row.id,
                "code": row.code,
                "device_id": device_id,
                "expires_at": row.expires_at,
            }
        logger.info(f"Agent enrollment started: {device_id} code={result['code']}")
        return result

    def poll_enrollment(self, pairing_id):
        """Agent polls its pairing. Returns ``{claimed: False}`` while pending; once claimed,
        returns ``{claimed: True, device_id, secret}`` exactly once, then deletes the row."""
        now = time.time()
        with session_scope() as s:
            row = s.get(PendingAgent, pairing_id)
            if not row:
                return {"claimed": False, "expired": True}
            if not row.claimed:
                if row.expires_at < now:
                    s.delete(row)
                    return {"claimed": False, "expired": True}
                return {"claimed": False, "code": row.code, "expires_at": row.expires_at}
            # Claimed — hand the secret over exactly once, then delete.
            payload = {
                "claimed": True,
                "device_id": row.device_id,
                "secret": row.issued_secret,
            }
            s.delete(row)
        return payload

    def list_pending_agents(self):
        self._prune_expired_pending()
        with session_scope() as s:
            rows = s.query(PendingAgent).filter_by(claimed=False).order_by(
                PendingAgent.created_at.desc()).all()
            return [r.to_dict() for r in rows]

    def claim_pending_agent(self, code, passphrase=None):
        """Operator claims a pairing code. Mints a secret, promotes the device, and marks the
        pending row claimed. Returns ``{device_id, ...}`` or raises ``ValueError``."""
        # Optional passphrase gate: when an API key is configured, require it to match.
        try:
            from config import API_KEY
        except Exception:
            API_KEY = ""
        if API_KEY and passphrase != API_KEY:
            raise ValueError("invalid passphrase")

        now = time.time()
        code = (code or "").strip().upper()
        with session_scope() as s:
            row = s.query(PendingAgent).filter_by(code=code, claimed=False).first()
            if not row:
                raise ValueError("unknown or already-claimed code")
            if row.expires_at < now:
                s.delete(row)
                raise ValueError("pairing code expired")
            device_id = row.device_id
            info = row.info or {}
            serial = row.serial
            ip = row.last_ip

        # Promote into the live registry + persist, then mint the secret.
        self.register_agent_device(
            device_id, info=info, serial=serial, ip=ip,
            capabilities=info.get("capabilities") or {})
        secret = self.issue_agent_secret(device_id)

        with session_scope() as s:
            row = s.query(PendingAgent).filter_by(code=code).first()
            if row:
                row.claimed = True
                row.issued_secret = secret

        try:
            self.notify_event(
                "agent.enrolled",
                data={"device_id": device_id,
                      "device_name": info.get("model") or device_id},
                subject_type="device", subject_id=device_id)
        except Exception:
            pass
        try:
            self.broadcast("agent_enrolled", {"device_id": device_id})
        except Exception:
            pass
        logger.info(f"Agent enrolled via pairing: {device_id}")
        return {"device_id": device_id, "enrolled": True}
