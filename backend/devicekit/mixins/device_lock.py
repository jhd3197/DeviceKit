import threading
import time
import uuid


class DeviceLockMixin:
    """Mutex-based device allocation for parallel test runners."""

    _device_locks = {}  # device_id -> {lock_id, owner, device_id, locked_at, timeout}
    _device_locks_lock = threading.Lock()
    DEFAULT_LOCK_TIMEOUT = 300  # 5 minutes

    def acquire_device_lock(self, device_id, owner, timeout=None):
        """
        Thread-safe device lock acquisition. Auto-expires stale locks.

        Returns lock dict on success, None if device is already locked.
        """
        if timeout is None:
            timeout = self.DEFAULT_LOCK_TIMEOUT

        with self._device_locks_lock:
            self._expire_stale_locks()

            existing = self._device_locks.get(device_id)
            if existing:
                return None

            lock_info = {
                'lock_id': str(uuid.uuid4()),
                'owner': owner,
                'device_id': device_id,
                'locked_at': time.time(),
                'timeout': timeout,
            }
            self._device_locks[device_id] = lock_info
            return lock_info

    def release_device_lock(self, device_id, owner=None, lock_id=None):
        """
        Release a device lock by matching owner or lock_id.

        Returns True if released, False if not found or mismatch.
        """
        with self._device_locks_lock:
            existing = self._device_locks.get(device_id)
            if not existing:
                return False

            if owner and existing['owner'] != owner:
                return False
            if lock_id and existing['lock_id'] != lock_id:
                return False

            del self._device_locks[device_id]
            return True

    def get_available_devices(self):
        """Return list of devices NOT currently locked."""
        with self._device_locks_lock:
            self._expire_stale_locks()
            locked_ids = set(self._device_locks.keys())

        all_devices = self.get_devices()
        return [d for d in all_devices if (d.get('serial') or d.get('device_id')) not in locked_ids]

    def get_device_lock_status(self, device_id):
        """Return lock info for a device, or None if unlocked."""
        with self._device_locks_lock:
            self._expire_stale_locks()
            return self._device_locks.get(device_id)

    def _expire_stale_locks(self):
        """Remove locks past their timeout. Must be called under _device_locks_lock."""
        now = time.time()
        expired = [
            did for did, lock in self._device_locks.items()
            if now - lock['locked_at'] > lock['timeout']
        ]
        for did in expired:
            del self._device_locks[did]
