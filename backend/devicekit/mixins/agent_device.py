"""On-device agent registry: live in-memory cache + persistence + command dispatch.

The live registry (``_agent_device_states`` and friends) is a lock-guarded in-memory cache
for fast SSE fan-out and heartbeat tracking, backed by ``AgentDevice`` rows so registered
devices survive a restart. Plan 02 lifted this registry out of the ``api_app()`` closure
onto the client; plan 07 hardens it with the ServerKit registry patterns:

* a background **heartbeat reaper** (``reap_stale_agents``) that marks a silent device
  offline *exactly once* — re-validating freshness under the registry lock so a quick
  reconnect isn't clobbered by a stale timeout;
* **reconnect correctness** — re-registering a device fails the old connection's in-flight
  commands with ``AGENT_RECONNECTED`` instead of letting callers hang;
* **synchronous command dispatch over async transport** — ``send_device_command`` blocks
  the caller on a ``queue.Queue`` while the agent polls the outbound queue and posts a
  result back, persisting every command as a ``DeviceCommand`` row (a device-action audit
  trail for free).

HMAC auth / key-rotation helpers (also plan 07) live alongside these.
"""
import time
import hmac
import hashlib
import secrets
import logging
import threading
import collections
from queue import Queue, Empty

from devicekit.db import session_scope
from devicekit.models import AgentDevice, DeviceCommand
from devicekit.agent_capabilities import (
    normalize_capabilities, extract_agent_version)

logger = logging.getLogger(__name__)


class AgentDeviceMixin:
    """Live agent-device registry + DB read/write helpers + command dispatch."""

    # -----------------------------------------------------------
    # Live registry (in-memory cache, hydrated from DB at boot)
    # -----------------------------------------------------------
    def init_agent_registry(self):
        """Create the in-memory registry and hydrate it from persisted rows.

        Called once from ``Client.__init__`` after persistence is up. Idempotent.
        """
        self._agent_device_states = {}
        self._agent_device_events = []
        self._agent_device_serial_index = {}  # serial -> device_id mapping
        self._agent_registry_lock = threading.RLock()
        # Server->agent outbound command queues (drained by the agent's poll).
        self._agent_outbound = collections.defaultdict(collections.deque)
        # In-flight synchronous commands: command_id -> {queue, device_id, conn_token}.
        self._agent_inflight = {}
        # Replay guard: seen nonces -> expiry epoch; per-IP auth-failure timestamps.
        self._agent_nonces = {}
        self._agent_auth_failures = collections.defaultdict(list)
        try:
            for row in self.load_agent_devices():
                did = row['device_id']
                serial = row.pop('serial', None)
                self._agent_device_states[did] = {
                    'device_id': did,
                    'info': row.get('info', {}),
                    'registered_at': row.get('registered_at'),
                    'last_heartbeat': row.get('last_heartbeat'),
                    'state': row.get('state', {}),
                    'online': row.get('online', False),
                    # Legacy rows may hold capabilities as an array; normalize to a map so
                    # every consumer (FQL, version view, negotiation) sees one shape.
                    'capabilities': normalize_capabilities(row.get('capabilities')),
                    'agent_version': row.get('agent_version'),
                    'agent_version_code': row.get('agent_version_code'),
                    'conn_token': 0,
                }
                if serial:
                    self._agent_device_serial_index[serial] = did
            if self._agent_device_states:
                logger.info(
                    f"Loaded {len(self._agent_device_states)} persisted agent device(s)"
                )
        except Exception as e:
            logger.warning(f"Could not load persisted agent devices: {e}")

    def _ensure_agent_registry(self):
        # Safety net if a code path reaches the registry before init_agent_registry().
        if not hasattr(self, '_agent_device_states'):
            self.init_agent_registry()

    def find_agent_device(self, device_id):
        """Find agent device state by device_id or serial-number cross-reference."""
        self._ensure_agent_registry()
        # Direct lookup
        if device_id in self._agent_device_states:
            return self._agent_device_states[device_id]
        # Try serial number index (ADB device IDs may be serial numbers)
        if device_id in self._agent_device_serial_index:
            mapped_id = self._agent_device_serial_index[device_id]
            return self._agent_device_states.get(mapped_id)
        # Fuzzy match: check if device_id is a substring of any agent device ID
        for agent_id, state in self._agent_device_states.items():
            if device_id in agent_id or agent_id in device_id:
                return state
            # Check serial in info
            info = state.get('info', {})
            if info.get('serial') == device_id:
                return state
        return None

    def _resolve_agent_device_id(self, device_id):
        """Map an ADB/serial id to the canonical agent device_id, if one exists."""
        state = self.find_agent_device(device_id)
        return state.get('device_id') if state else device_id

    # -----------------------------------------------------------
    # Registration (reconnect-aware)
    # -----------------------------------------------------------
    def register_agent_device(self, device_id, info, serial=None, ip=None,
                              capabilities=None, secret=None):
        """Register (or reconnect) an agent device.

        On reconnect the old connection's in-flight commands are failed with
        ``AGENT_RECONNECTED`` (ServerKit's fix — callers get a definitive error instead of
        hanging on a dead socket). State/registered_at are preserved across a reconnect.
        Returns a summary dict.
        """
        self._ensure_agent_registry()
        now = time.time()
        raw_caps = capabilities if capabilities is not None else (info or {}).get('capabilities')
        # Accept a legacy array or a map; the rest of the platform expects a map (FQL `can.*`,
        # capability gating, batched-survey negotiation).
        capabilities = normalize_capabilities(raw_caps)
        version_name, version_code = extract_agent_version(info)
        with self._agent_registry_lock:
            prev = self._agent_device_states.get(device_id)
            reconnected = prev is not None
            was_offline = (prev is None) or (not prev.get('online'))
            old_token = prev.get('conn_token', 0) if prev else 0
            token = old_token + 1
            self._agent_device_states[device_id] = {
                'device_id': device_id,
                'info': info or {},
                'registered_at': prev.get('registered_at', now) if prev else now,
                'last_heartbeat': now,
                'state': prev.get('state', {}) if prev else {},
                'online': True,
                'capabilities': capabilities,
                'agent_version': version_name,
                'agent_version_code': version_code,
                'conn_token': token,
            }
            if serial:
                self._agent_device_serial_index[serial] = device_id

        # Fail the previous connection's in-flight commands (outside the lock — they own
        # their own queues).
        if reconnected:
            self._fail_inflight_commands(device_id, 'AGENT_RECONNECTED', conn_token=old_token)

        self.save_agent_device(
            device_id, info=info or {}, serial=serial,
            registered_at=self._agent_device_states[device_id]['registered_at'],
            last_heartbeat=now, state=self._agent_device_states[device_id]['state'],
            online=True, capabilities=capabilities, last_ip=ip, secret=secret,
            agent_version=version_name, agent_version_code=version_code,
        )
        return {
            'device_id': device_id,
            'reconnected': reconnected,
            'was_offline': was_offline,
            'conn_token': token,
        }

    def touch_agent_heartbeat(self, device_id, state=None, online=True):
        """Refresh last_heartbeat (and optionally state) under the registry lock. Returns
        True if the device was online->offline recovering (so callers can emit device.online)."""
        self._ensure_agent_registry()
        now = time.time()
        recovered = False
        with self._agent_registry_lock:
            d = self._agent_device_states.get(device_id)
            if not d:
                return None
            recovered = online and not d.get('online')
            d['last_heartbeat'] = now
            d['online'] = online
            if state is not None:
                d['state'] = state
        fields = {'last_heartbeat': now, 'online': online}
        if state is not None:
            fields['state'] = state
        self.update_agent_device_fields(device_id, **fields)
        return recovered

    # -----------------------------------------------------------
    # Heartbeat reaper (marks stale devices offline exactly once)
    # -----------------------------------------------------------
    def reap_stale_agents(self, timeout=None):
        """Mark every device with no heartbeat in ``timeout`` seconds offline — exactly once.

        Two race fixes ported from ServerKit's reaper:
        * Freshness is re-validated **under the registry lock**: a concurrent heartbeat
          (also taken under the lock) updates ``last_heartbeat``/``online`` atomically, so a
          device that just reconnected is skipped instead of being evicted by a stale sweep.
        * Only an ``online -> offline`` transition emits ``device.offline`` — an
          already-offline device never re-notifies, so a quick reconnect can't flap.

        DB writes / broadcasts / notifications happen after the lock is released.
        """
        self._ensure_agent_registry()
        if timeout is None:
            try:
                from config import AGENT_HEARTBEAT_TIMEOUT
                timeout = AGENT_HEARTBEAT_TIMEOUT
            except Exception:
                timeout = 90.0
        now = time.time()
        evicted = []
        with self._agent_registry_lock:
            for did, state in self._agent_device_states.items():
                last_hb = state.get('last_heartbeat') or 0
                if state.get('online') and (now - last_hb) > timeout:
                    state['online'] = False
                    evicted.append((did, state.get('conn_token', 0)))

        for did, token in evicted:
            self._fail_inflight_commands(did, 'AGENT_OFFLINE', conn_token=token)
            try:
                self.update_agent_device_fields(did, online=False)
            except Exception as e:
                logger.debug(f"reaper persist offline failed for {did}: {e}")
            try:
                self.broadcast('device_disconnected', {'device_id': did})
            except Exception:
                pass
            try:
                self.notify_event(
                    'device.offline',
                    data={'device_id': did, 'device_name': self._agent_device_name(did)},
                    subject_type='device', subject_id=did)
            except Exception:
                pass
            logger.info(f"Agent device offline (no heartbeat > {timeout}s): {did}")
        return [d for d, _ in evicted]

    def _agent_device_name(self, device_id):
        try:
            info = (self._agent_device_states.get(device_id) or {}).get('info') or {}
            return info.get('model') or device_id
        except Exception:
            return device_id

    # -----------------------------------------------------------
    # Synchronous command dispatch over async (poll) transport
    # -----------------------------------------------------------
    def send_device_command(self, device_id, command, args=None, timeout=None,
                            source='api'):
        """Dispatch a command to an agent and block until it posts a result (or times out).

        Persists a ``DeviceCommand`` row through pending->running->completed/failed/timeout.
        The agent picks the command up on its next poll (``drain_outbound_commands``) and
        posts the result back through ``resolve_device_command``.
        """
        self._ensure_agent_registry()
        if timeout is None:
            try:
                from config import AGENT_COMMAND_TIMEOUT
                timeout = AGENT_COMMAND_TIMEOUT
            except Exception:
                timeout = 30.0
        did = self._resolve_agent_device_id(device_id)
        cmd_id = self.create_device_command(did, command, args or {}, source=source)

        q = Queue(maxsize=1)
        with self._agent_registry_lock:
            state = self._agent_device_states.get(did)
            token = state.get('conn_token', 0) if state else 0
            online = bool(state and state.get('online'))
            self._agent_inflight[cmd_id] = {
                'queue': q, 'device_id': did, 'conn_token': token}
            self._agent_outbound[did].append(
                {'id': cmd_id, 'command': command, 'args': args or {}})

        if not online:
            self._pop_inflight(cmd_id)
            self.update_device_command(cmd_id, status=DeviceCommand.STATUS_FAILED,
                                       error='AGENT_OFFLINE')
            return self.get_device_command(cmd_id)

        self.update_device_command(cmd_id, status=DeviceCommand.STATUS_RUNNING,
                                   started_at=time.time())
        try:
            outcome = q.get(timeout=timeout)
        except Empty:
            self._pop_inflight(cmd_id)
            # Leave the command in the outbound queue removed so a late poll doesn't resend.
            self._discard_outbound(did, cmd_id)
            self.update_device_command(cmd_id, status=DeviceCommand.STATUS_TIMEOUT,
                                       error=f'timeout after {timeout}s',
                                       completed_at=time.time())
            return self.get_device_command(cmd_id)

        self._pop_inflight(cmd_id)
        if outcome.get('error'):
            self.update_device_command(cmd_id, status=DeviceCommand.STATUS_FAILED,
                                       error=str(outcome['error']),
                                       completed_at=time.time())
        else:
            self.update_device_command(cmd_id, status=DeviceCommand.STATUS_COMPLETED,
                                       result=outcome.get('result'),
                                       completed_at=time.time())
        return self.get_device_command(cmd_id)

    def resolve_device_command(self, command_id, result=None, error=None):
        """Agent-posted result for an in-flight (or already-terminal) command."""
        self._ensure_agent_registry()
        with self._agent_registry_lock:
            entry = self._agent_inflight.get(command_id)
        if entry is not None:
            try:
                entry['queue'].put_nowait({'result': result, 'error': error})
            except Exception:
                pass
            return True
        # No waiter (already timed out / reaped) — still record the late result durably.
        row = self.get_device_command(command_id)
        if not row:
            return False
        if row['status'] not in DeviceCommand.TERMINAL_STATUSES:
            self.update_device_command(
                command_id,
                status=DeviceCommand.STATUS_FAILED if error else DeviceCommand.STATUS_COMPLETED,
                result=result, error=error, completed_at=time.time())
        return True

    def drain_outbound_commands(self, device_id, max_commands=10):
        """Return (and remove) queued commands for the agent to execute on this poll."""
        self._ensure_agent_registry()
        did = self._resolve_agent_device_id(device_id)
        out = []
        with self._agent_registry_lock:
            dq = self._agent_outbound.get(did)
            while dq and len(out) < max_commands:
                out.append(dq.popleft())
        return out

    def _discard_outbound(self, device_id, command_id):
        with self._agent_registry_lock:
            dq = self._agent_outbound.get(device_id)
            if dq:
                self._agent_outbound[device_id] = collections.deque(
                    c for c in dq if c.get('id') != command_id)

    def _pop_inflight(self, command_id):
        with self._agent_registry_lock:
            return self._agent_inflight.pop(command_id, None)

    def _fail_inflight_commands(self, device_id, reason, conn_token=None):
        """Fail every in-flight command for a device (optionally only a given connection)."""
        self._ensure_agent_registry()
        to_fail = []
        with self._agent_registry_lock:
            for cid, entry in list(self._agent_inflight.items()):
                if entry['device_id'] != device_id:
                    continue
                if conn_token is not None and entry.get('conn_token') != conn_token:
                    continue
                to_fail.append((cid, entry))
                self._agent_inflight.pop(cid, None)
            # Drop any still-queued outbound commands for a dead connection.
            if conn_token is not None:
                self._agent_outbound.pop(device_id, None)
        for cid, entry in to_fail:
            try:
                entry['queue'].put_nowait({'error': reason})
            except Exception:
                pass

    # -----------------------------------------------------------
    # DeviceCommand persistence (audit trail)
    # -----------------------------------------------------------
    def create_device_command(self, device_id, command, args=None, source='api'):
        now = time.time()
        with session_scope() as s:
            row = DeviceCommand(device_id=device_id, command=command, args=args or {},
                                status=DeviceCommand.STATUS_PENDING, source=source,
                                created_at=now)
            s.add(row)
            s.flush()
            return row.id

    def update_device_command(self, command_id, **fields):
        with session_scope() as s:
            row = s.get(DeviceCommand, command_id)
            if not row:
                return False
            for key in ("status", "result", "error", "started_at", "completed_at"):
                if key in fields:
                    setattr(row, key, fields[key])
            return True

    def get_device_command(self, command_id):
        with session_scope() as s:
            row = s.get(DeviceCommand, command_id)
            return row.to_dict() if row else None

    def list_device_commands(self, device_id=None, status=None, limit=100, offset=0):
        with session_scope() as s:
            q = s.query(DeviceCommand)
            if device_id:
                did = self._resolve_agent_device_id(device_id)
                q = q.filter(DeviceCommand.device_id == did)
            if status:
                q = q.filter(DeviceCommand.status == status)
            q = q.order_by(DeviceCommand.created_at.desc()).offset(offset).limit(limit)
            return [r.to_dict() for r in q.all()]

    def count_device_commands(self, device_id=None, status=None):
        with session_scope() as s:
            q = s.query(DeviceCommand)
            if device_id:
                q = q.filter(DeviceCommand.device_id == self._resolve_agent_device_id(device_id))
            if status:
                q = q.filter(DeviceCommand.status == status)
            return q.count()

    # -----------------------------------------------------------
    # HMAC auth + per-device secrets + key rotation (plan 07)
    # -----------------------------------------------------------
    @staticmethod
    def _generate_secret():
        return secrets.token_hex(32)

    @staticmethod
    def compute_agent_signature(secret, device_id, timestamp, nonce):
        """HMAC-SHA256 over ``device_id:timestamp:nonce`` — the agent signs the same string."""
        msg = f"{device_id}:{timestamp}:{nonce}".encode()
        return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    def get_agent_secret(self, device_id):
        """Return the active (and pending, if rotating) secret for a device."""
        with session_scope() as s:
            row = s.get(AgentDevice, self._resolve_agent_device_id(device_id))
            if not row:
                return None
            return {'secret': row.secret, 'secret_pending': row.secret_pending}

    def issue_agent_secret(self, device_id):
        """Mint and store a fresh per-device secret (used at enrollment)."""
        secret = self._generate_secret()
        with session_scope() as s:
            row = s.get(AgentDevice, device_id)
            if row:
                row.secret = secret
                row.secret_pending = None
                row.secret_rotated_at = None
        return secret

    def verify_agent_signature(self, device_id, timestamp, nonce, signature, window=None):
        """Verify an agent HMAC signature, accepting either the active or a pending
        (rotating) secret. Returns True/False. Does NOT consume the nonce — the caller
        checks replay separately so the signature is validated *before* the nonce is
        consumed (ServerKit's documented subtle fix)."""
        creds = self.get_agent_secret(device_id)
        if not creds or not creds.get('secret'):
            return False
        for candidate in (creds.get('secret'), creds.get('secret_pending')):
            if not candidate:
                continue
            expected = self.compute_agent_signature(candidate, device_id, timestamp, nonce)
            if hmac.compare_digest(expected, signature or ''):
                return True
        return False

    def verify_agent_request(self, device_id, timestamp, nonce, signature, ip=None,
                             window=None):
        """Full request auth: rate-limit → timestamp window → signature (before nonce
        consumption) → nonce replay. Returns ``(ok, error_message)``.

        Order matters: the HMAC signature is checked *before* the nonce is marked consumed,
        so a forged request can never burn a legitimate agent's nonce (ServerKit's fix).
        """
        self._ensure_agent_registry()
        try:
            from config import AGENT_HMAC_WINDOW
        except Exception:
            AGENT_HMAC_WINDOW = 60.0
        window = window if window is not None else AGENT_HMAC_WINDOW
        now = time.time()

        # Per-IP rate limit on auth attempts (20 / 60s window).
        if ip is not None:
            with self._agent_registry_lock:
                fails = self._agent_auth_failures[ip]
                fails[:] = [t for t in fails if now - t < 60]
                if len(fails) >= 20:
                    return False, 'rate limited'

        def _fail(msg):
            if ip is not None:
                with self._agent_registry_lock:
                    self._agent_auth_failures[ip].append(now)
            logger.warning(f"Agent auth failure for {device_id} from {ip}: {msg}")
            return False, msg

        if not timestamp or not nonce or not signature:
            return _fail('missing auth headers')

        # Timestamp window (reject stale / far-future).
        try:
            ts = float(timestamp)
        except (TypeError, ValueError):
            return _fail('bad timestamp')
        if abs(now - ts) > window:
            return _fail('timestamp outside window')

        # Signature — validated BEFORE the nonce is consumed.
        if not self.verify_agent_signature(device_id, timestamp, nonce, signature, window=window):
            return _fail('bad signature')

        # Nonce replay check + consume (only now that the signature is proven valid).
        with self._agent_registry_lock:
            # Opportunistic GC of expired nonces.
            if len(self._agent_nonces) > 4096:
                self._agent_nonces = {n: exp for n, exp in self._agent_nonces.items() if exp > now}
            key = f"{device_id}:{nonce}"
            if self._agent_nonces.get(key, 0) > now:
                return _fail('nonce replay')
            self._agent_nonces[key] = now + window * 2

        # Record last IP for anomaly visibility (new-IP detection is a future enhancement).
        if ip is not None:
            try:
                self.update_agent_device_fields(self._resolve_agent_device_id(device_id), last_ip=ip)
            except Exception:
                pass
        return True, None

    def start_key_rotation(self, device_id):
        """Stage a new secret without dropping the current one (zero-downtime rotation)."""
        did = self._resolve_agent_device_id(device_id)
        new_secret = self._generate_secret()
        with session_scope() as s:
            row = s.get(AgentDevice, did)
            if not row:
                return None
            row.secret_pending = new_secret
            row.secret_rotated_at = time.time()
        return new_secret

    def complete_key_rotation(self, device_id):
        """Promote the pending secret to active and clear the old one."""
        did = self._resolve_agent_device_id(device_id)
        with session_scope() as s:
            row = s.get(AgentDevice, did)
            if not row or not row.secret_pending:
                return False
            row.secret = row.secret_pending
            row.secret_pending = None
            row.secret_rotated_at = None
            return True

    # -----------------------------------------------------------
    # Capabilities (plan 07)
    # -----------------------------------------------------------
    def update_agent_capabilities(self, device_id, capabilities):
        did = self._resolve_agent_device_id(device_id)
        with self._agent_registry_lock:
            st = self._agent_device_states.get(did)
            if st is not None:
                st['capabilities'] = capabilities or {}
        self.update_agent_device_fields(did, capabilities=capabilities or {})

    def get_agent_capabilities(self, device_id):
        state = self.find_agent_device(device_id)
        return (state or {}).get('capabilities', {}) or {}

    # -----------------------------------------------------------
    # Persistence helpers
    # -----------------------------------------------------------
    def load_agent_devices(self):
        """Return all persisted agent-device rows as dicts (with serial for indexing)."""
        with session_scope() as s:
            out = []
            for row in s.query(AgentDevice).all():
                d = row.to_dict()
                d["serial"] = row.serial
                out.append(d)
            return out

    def save_agent_device(self, device_id, info, serial=None, registered_at=None,
                          last_heartbeat=None, state=None, online=True,
                          capabilities=None, last_ip=None, secret=None,
                          agent_version=None, agent_version_code=None):
        """Upsert an agent device (used on registration)."""
        now = time.time()
        with session_scope() as s:
            row = s.get(AgentDevice, device_id)
            if not row:
                row = AgentDevice(device_id=device_id, registered_at=registered_at or now)
                s.add(row)
            row.info = info or {}
            row.serial = serial
            row.state = state or {}
            row.last_heartbeat = last_heartbeat if last_heartbeat is not None else now
            row.online = online
            if capabilities is not None:
                row.capabilities = capabilities or {}
            if last_ip is not None:
                row.last_ip = last_ip
            if secret is not None:
                row.secret = secret
            # Only overwrite the advertised version when the agent actually sent one, so a
            # legacy re-register that omits it doesn't blank a known version.
            if agent_version is not None:
                row.agent_version = agent_version
            if agent_version_code is not None:
                row.agent_version_code = agent_version_code

    def update_agent_device_fields(self, device_id, **fields):
        """Partial update of a persisted agent device (state, last_heartbeat, online)."""
        with session_scope() as s:
            row = s.get(AgentDevice, device_id)
            if not row:
                return False
            for key in ("info", "state", "last_heartbeat", "online", "serial",
                        "capabilities", "last_ip", "secret",
                        "agent_version", "agent_version_code"):
                if key in fields:
                    setattr(row, key, fields[key])
            return True

    # -----------------------------------------------------------
    # Fleet version view (plan 25 part 2): which agent version is on which device
    # -----------------------------------------------------------
    def list_agent_versions(self):
        """Per-device agent version + an aggregate ``version → [device_ids]`` rollup.

        Backs the fleet "which agent version where" view and the OTA rollout targeting
        (plan 25 phase 3). Reads the live registry so online/offline is current.
        """
        self._ensure_agent_registry()
        with self._agent_registry_lock:
            states = [dict(s) for s in self._agent_device_states.values()]
        devices = []
        rollup = {}
        for st in states:
            did = st.get('device_id')
            version = st.get('agent_version')
            code = st.get('agent_version_code')
            info = st.get('info') or {}
            devices.append({
                'device_id': did,
                'agent_version': version,
                'agent_version_code': code,
                'online': bool(st.get('online')),
                'model': info.get('model'),
                'android_api': (st.get('capabilities') or {}).get('android_api')
                               or info.get('sdk'),
                'capabilities': st.get('capabilities') or {},
            })
        for d in devices:
            key = d['agent_version'] or 'unknown'
            bucket = rollup.setdefault(key, {'version': key, 'count': 0,
                                             'online': 0, 'device_ids': []})
            bucket['count'] += 1
            bucket['device_ids'].append(d['device_id'])
            if d['online']:
                bucket['online'] += 1
        devices.sort(key=lambda d: (d['agent_version'] or '', d['device_id'] or ''))
        return {
            'devices': devices,
            'versions': sorted(rollup.values(), key=lambda v: v['version']),
            'distinct_versions': len(rollup),
        }
