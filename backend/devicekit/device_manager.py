import threading
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DeviceManager:
    def __init__(self, devices: list):
        self.devices = {
            device_id: {
                'status': 'available',
                'port': 9222 + idx,
                'lock': threading.Lock(),
                'last_taken': None,
                'timer': None
            }
            for idx, device_id in enumerate(devices)
        }
        self.manager_lock = threading.Lock()
        self.DEVICE_TIMEOUT = 450  # 7.5 minutes
        self.LOCK_TIMEOUT = 30

    def _start_device_timer(self, device_id: str):
        """Start a timer thread for the device to auto-release if not freed."""
        def timer_thread():
            time.sleep(self.DEVICE_TIMEOUT)
            with self.manager_lock:
                if (self.devices[device_id]['status'] == 'busy' and
                        time.time() - self.devices[device_id]['last_taken'] >= self.DEVICE_TIMEOUT):
                    logger.warning(f"Force releasing device {device_id} after timeout")
                    self.release_device(device_id)

        self.devices[device_id]['last_taken'] = time.time()
        self.devices[device_id]['timer'] = threading.Thread(target=timer_thread, daemon=True)
        self.devices[device_id]['timer'].start()

    def get_available_device(self) -> Optional[tuple]:
        """Return (device_id, port) for the first available device, or None."""
        try:
            if not self.manager_lock.acquire(timeout=self.LOCK_TIMEOUT):
                logger.error("Timeout acquiring manager lock in get_available_device")
                return None
            try:
                for device_id, info in self.devices.items():
                    if info['status'] == 'available':
                        info['status'] = 'busy'
                        self._start_device_timer(device_id)
                        logger.info(f"Device {device_id} taken and set to busy.")
                        return device_id, info['port']
                logger.warning("No available devices found")
                return None
            finally:
                self.manager_lock.release()
        except Exception as e:
            logger.error(f"Error in get_available_device: {e}")
            if self.manager_lock.locked():
                self.manager_lock.release()
            return None

    def release_device(self, device_id: str) -> bool:
        """Release the given device, marking it as 'available'."""
        try:
            if not self.manager_lock.acquire(timeout=self.LOCK_TIMEOUT):
                logger.error(f"Timeout acquiring manager lock for device {device_id}")
                return False
            try:
                if device_id in self.devices:
                    device_info = self.devices[device_id]
                    device_info['status'] = 'available'
                    device_info['last_taken'] = None
                    device_info['timer'] = None
                    logger.info(f"Device {device_id} released.")
                    return True
            finally:
                self.manager_lock.release()
        except Exception as e:
            logger.error(f"Error releasing device {device_id}: {e}")
            if self.manager_lock.locked():
                self.manager_lock.release()
            return False

    def get_current_device_status(self) -> list:
        """Return a list of (device_id, status, port)."""
        return [(did, info['status'], info['port']) for did, info in self.devices.items()]

    def get_device_port(self, device_id: str) -> Optional[int]:
        return self.devices.get(device_id, {}).get('port')

    def has_available_device(self) -> bool:
        with self.manager_lock:
            return any(info['status'] == 'available' for info in self.devices.values())

    @property
    def available_count(self) -> int:
        with self.manager_lock:
            return sum(1 for info in self.devices.values() if info['status'] == 'available')
