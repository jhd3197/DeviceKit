import io
import time
import logging
import tempfile
import os

try:
    import uiautomator2 as u2
except ImportError:
    u2 = None

logger = logging.getLogger(__name__)


class Uiautomator2Mixin:
    devices = {}
    devices_metadata = {}

    def start_uiautomator2_server(self):
        """Start UIAutomator2 server on all connected devices."""
        adb_devices = self.get_connected_devices()
        for device_id in adb_devices:
            try:
                self.get_device(device_id)
                logger.info(f"Started UIAutomator2 server on device {device_id}")
            except Exception as e:
                logger.error(f"Failed to start UIAutomator2 on {device_id}: {e}")

    def get_devices(self):
        """Get list of connected devices with metadata."""
        devices = []
        for device_id in self.devices:
            device_info = self.get_device_info(device_id)
            if device_info and device_id in self.devices_metadata:
                device_info.update(self.devices_metadata[device_id])
            if device_info:
                devices.append(device_info)
        return devices

    def get_device(self, device_id):
        """Get or create a device connection."""
        if device_id not in self.devices:
            if u2 is None:
                raise RuntimeError("uiautomator2 is not installed. Install it with: pip install uiautomator2")
            try:
                self.devices[device_id] = u2.connect(device_id)
                self.devices_metadata[device_id] = {
                    'ip': None,
                    'location': None,
                    'port': 9222 + len(self.devices) - 1
                }
                logger.info(f"Connected to device {device_id}")
            except Exception as e:
                logger.error(f"Failed to connect to device {device_id}: {e}")
                raise
        return self.devices[device_id]

    def get_device_vpn_metadata(self, device_id):
        """Get metadata for a device."""
        return self.devices_metadata.get(device_id)

    def get_device_info(self, device_id):
        """Get detailed device information."""
        try:
            d = self.get_device(device_id)
            info = d.info
            return {
                'device_id': device_id,
                'name': info.get('productName'),
                'screenOn': info.get('screenOn'),
                'sdkInt': info.get('sdkInt'),
                'naturalOrientation': info.get('naturalOrientation'),
                'currentPackageName': info.get('currentPackageName'),
                'display': {
                    'width': info.get('displayWidth'),
                    'height': info.get('displayHeight'),
                    'rotation': info.get('displayRotation'),
                    'dpx': info.get('displaySizeDpX'),
                    'dpy': info.get('displaySizeDpY'),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get device info for {device_id}: {e}")
            return None

    def click(self, x, y, device_id):
        d = self.get_device(device_id)
        d.click(x, y)

    def exists_by_resource_id(self, resource_id, device_id, timeout=10):
        try:
            d = self.get_device(device_id)
            return d(resourceId=resource_id).exists(timeout=timeout)
        except Exception:
            return False

    def click_by_resource_id(self, resource_id, device_id):
        d = self.get_device(device_id)
        d(resourceId=resource_id).click()

    def exists_by_text(self, text, device_id, timeout=10):
        try:
            d = self.get_device(device_id)
            return d(text=text).exists(timeout=timeout)
        except Exception:
            return False

    def click_by_text(self, text, device_id):
        d = self.get_device(device_id)
        d(text=text).click()

    def press_action(self, action, device_id):
        d = self.get_device(device_id)
        d.press(action)

    def start_chrome_browser(self, url, device_id):
        """Start Chrome and navigate to URL."""
        try:
            d = self.get_device(device_id)
            time.sleep(1)
            d.app_start("com.android.chrome")
            time.sleep(1)
            if self.exists_by_resource_id("com.android.chrome:id/search_box", device_id):
                self.click_by_resource_id("com.android.chrome:id/search_box", device_id)
            elif self.exists_by_resource_id("com.android.chrome:id/location_bar", device_id):
                self.click_by_resource_id("com.android.chrome:id/location_bar", device_id)
            time.sleep(1)
            d.send_keys(url)
            time.sleep(1)
            self.press_action("enter", device_id)
        except Exception as e:
            logger.error(f"Failed to open Chrome on {device_id}: {e}")
            raise

    def forward_devtools_port(self, device_id=None, local_port=9222):
        self.run_adb_command(
            ["forward", f"tcp:{local_port}", "localabstract:chrome_devtools_remote"],
            device=device_id
        )

    def restart_chrome_browser(self, url, device_id, local_port=9222):
        self.run_adb_command(["shell", "am", "force-stop", "com.android.chrome"], device=device_id)
        self.run_adb_command(["forward", "--remove-all"], device=device_id)
        time.sleep(1)
        self.start_chrome_browser(url, device_id)
        time.sleep(2)
        self.run_adb_command(
            ["forward", f"tcp:{local_port}", "localabstract:chrome_devtools_remote"],
            device=device_id
        )

    def is_app_installed(self, package_name, device_id):
        try:
            d = self.get_device(device_id)
            app_info = d.app_info(package_name)
            return app_info.get("versionName") is not None
        except Exception:
            return False

    def take_screenshot(self, device_id):
        """Take a screenshot and return the image bytes."""
        try:
            d = self.get_device(device_id)
            img = d.screenshot()
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Screenshot failed for {device_id}: {e}")
            return None

    def get_device_model(self, device_id):
        """Get device model string."""
        output = self.run_adb_command(["shell", "getprop", "ro.product.model"], device=device_id)
        return output.strip() if output else "Unknown"
