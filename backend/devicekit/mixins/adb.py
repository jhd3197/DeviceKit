import subprocess
import logging

logger = logging.getLogger(__name__)


class AdbMixin:
    def run_adb_command(self, args, device=None):
        """Run an ADB command and return stdout."""
        cmd = ["adb"]
        if device:
            cmd.extend(["-s", device])

        if isinstance(args, str):
            args = args.strip().split()
        elif not isinstance(args, list):
            raise ValueError("args must be a list or a string")

        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            logger.info(f"ADB: {' '.join(cmd)}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"ADB command timed out: {' '.join(cmd)}")
            return ""
        except subprocess.CalledProcessError as e:
            logger.error(f"ADB command failed: {' '.join(cmd)} - {e}")
            return ""

    def get_connected_devices(self):
        """Get list of connected devices using ADB."""
        try:
            output = subprocess.check_output(["adb", "devices"]).decode('utf-8')
            lines = output.strip().split('\n')[1:]
            devices = []
            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2 and parts[1].strip() == 'device':
                        devices.append(parts[0])
            logger.info(f"Found {len(devices)} connected devices")
            return devices
        except Exception as e:
            logger.error(f"Error getting device list: {e}")
            return []

    def start_chrome(self, url, device=None):
        """Launch Chrome with the given URL."""
        self.run_adb_command([
            "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", url,
            "com.android.chrome"
        ], device=device)

    def forward_devtools_port_adb(self, device=None, local_port=9222):
        """Forward local tcp port to Chrome DevTools socket."""
        self.run_adb_command([
            "forward", f"tcp:{local_port}",
            "localabstract:chrome_devtools_remote"
        ], device=device)

    def swipe_up(self, device=None, duration=500):
        """Perform a swipe up gesture."""
        try:
            output = subprocess.check_output(
                ["adb"] + (["-s", device] if device else []) + ["shell", "wm", "size"]
            ).decode('utf-8')
            width, height = map(int, output.strip().split(': ')[1].split('x'))
            start_x = width // 2
            start_y = height * 3 // 4
            end_x = width // 2
            end_y = height // 4
            self.run_adb_command([
                "shell", "input", "swipe",
                str(start_x), str(start_y), str(end_x), str(end_y), str(duration)
            ], device=device)
        except Exception as e:
            logger.error(f"Error performing swipe: {e}")

    def stop_chrome(self, device=None):
        """Force-stop Chrome browser."""
        self.run_adb_command(
            ["shell", "am", "force-stop", "com.android.chrome"],
            device=device or getattr(self, 'device', None)
        )

    def get_device_battery(self, device=None):
        """Get battery info from device."""
        output = self.run_adb_command(["shell", "dumpsys", "battery"], device=device)
        info = {}
        for line in output.split('\n'):
            line = line.strip()
            if ':' in line:
                key, val = line.split(':', 1)
                info[key.strip().lower().replace(' ', '_')] = val.strip()
        return info

    def reboot_device(self, device=None):
        """Reboot the device via ADB."""
        self.run_adb_command(["reboot"], device=device)
