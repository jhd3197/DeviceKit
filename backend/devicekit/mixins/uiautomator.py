import io
import time
import logging
import tempfile
import os

import requests

try:
    import uiautomator2 as u2
except ImportError:
    u2 = None

logger = logging.getLogger(__name__)

GITHUB_RELEASES_API = "https://api.github.com/repos/jhd3197/DeviceKit/releases/latest"
APK_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".apk_cache")


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

    # ------------------------------------------------------------------
    # Agent APK onboarding
    # ------------------------------------------------------------------
    def get_installed_agent_version(self, device_id):
        """Get the installed version of com.devicekit.agent, or None."""
        try:
            d = self.get_device(device_id)
            app_info = d.app_info("com.devicekit.agent")
            return app_info.get("versionName") if app_info else None
        except Exception:
            return None

    def download_latest_agent_apk(self):
        """Download the latest agent APK from GitHub Releases.

        Returns dict with keys: path, version, cached (bool), error (str|None).
        """
        os.makedirs(APK_CACHE_DIR, exist_ok=True)
        try:
            resp = requests.get(GITHUB_RELEASES_API, timeout=15)
            resp.raise_for_status()
            release = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch latest release info: {e}")
            return {"path": None, "version": None, "cached": False, "error": str(e)}

        version = release.get("tag_name", "unknown")
        assets = release.get("assets", [])

        # Find the release APK asset
        apk_asset = None
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith("-release.apk") or (name.endswith(".apk") and "release" in name.lower()):
                apk_asset = asset
                break
        # Fallback: any .apk file
        if apk_asset is None:
            for asset in assets:
                if asset.get("name", "").endswith(".apk"):
                    apk_asset = asset
                    break

        if apk_asset is None:
            logger.error(f"No APK asset found in release {version}")
            return {"path": None, "version": version, "cached": False, "error": "No APK asset in release"}

        filename = f"{version}_{apk_asset['name']}"
        local_path = os.path.join(APK_CACHE_DIR, filename)

        # Return cached file if it already exists
        if os.path.isfile(local_path):
            logger.info(f"Using cached APK: {local_path}")
            return {"path": local_path, "version": version, "cached": True, "error": None}

        # Download the APK
        download_url = apk_asset.get("browser_download_url")
        logger.info(f"Downloading agent APK {version} from {download_url}")
        try:
            dl = requests.get(download_url, timeout=60, stream=True)
            dl.raise_for_status()
            tmp_path = local_path + ".tmp"
            with open(tmp_path, "wb") as f:
                for chunk in dl.iter_content(chunk_size=8192):
                    f.write(chunk)
            os.replace(tmp_path, local_path)
            logger.info(f"APK downloaded to {local_path}")
            return {"path": local_path, "version": version, "cached": False, "error": None}
        except Exception as e:
            logger.error(f"Failed to download APK: {e}")
            if os.path.exists(local_path + ".tmp"):
                os.remove(local_path + ".tmp")
            return {"path": None, "version": version, "cached": False, "error": str(e)}

    def ensure_agent_installed(self, device_id):
        """Ensure com.devicekit.agent is installed (and up-to-date) on the device.

        Returns dict with status info.
        """
        installed_version = self.get_installed_agent_version(device_id)

        # Download latest release info + APK
        apk_info = self.download_latest_agent_apk()
        if apk_info["error"]:
            logger.warning(f"Could not download agent APK for {device_id}: {apk_info['error']}")
            return {
                "device_id": device_id,
                "action": "error",
                "installed_version": installed_version,
                "error": apk_info["error"],
            }

        latest_version = apk_info["version"]

        # Already installed and up-to-date
        if installed_version and installed_version == latest_version:
            logger.info(f"Agent on {device_id} already up-to-date ({installed_version})")
            return {
                "device_id": device_id,
                "action": "already_up_to_date",
                "installed_version": installed_version,
                "latest_version": latest_version,
            }

        # Need install or upgrade
        action = "upgrade" if installed_version else "install"
        logger.info(f"Agent {action} on {device_id}: {installed_version} -> {latest_version}")

        success, output = self.install_apk(apk_info["path"], device=device_id)

        if success:
            self.log_activity(f"agent_{action}", device_id, {
                "previous_version": installed_version,
                "new_version": latest_version,
            })

        return {
            "device_id": device_id,
            "action": action,
            "success": success,
            "installed_version": installed_version,
            "latest_version": latest_version,
            "output": output,
        }

    def get_agent_apk_cache_status(self):
        """Return info about the cached APK and latest release version."""
        cached_files = []
        if os.path.isdir(APK_CACHE_DIR):
            for f in os.listdir(APK_CACHE_DIR):
                if f.endswith(".apk"):
                    full = os.path.join(APK_CACHE_DIR, f)
                    cached_files.append({
                        "filename": f,
                        "size_bytes": os.path.getsize(full),
                    })

        # Fetch latest release version
        latest_version = None
        try:
            resp = requests.get(GITHUB_RELEASES_API, timeout=10)
            resp.raise_for_status()
            latest_version = resp.json().get("tag_name")
        except Exception:
            pass

        return {
            "cache_dir": APK_CACHE_DIR,
            "cached_files": cached_files,
            "latest_version": latest_version,
        }
