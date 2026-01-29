"""CLI tool for droidlink."""

import argparse
import json
import sys

from . import __version__


def cmd_devices(args):
    from . import devices
    devs = devices()
    if not devs:
        print("No devices found.")
        return
    for d in devs:
        print(f"  {d['serial']}  model={d.get('model', '?')}  device={d.get('device', '?')}")


def cmd_ping(args):
    from . import connect, connect_wifi
    try:
        if args.wifi:
            d = connect_wifi(args.wifi)
        else:
            d = connect(serial=args.serial)
        print(f"OK - Agent responding on {d}")
    except Exception as e:
        print(f"FAIL - {e}")
        sys.exit(1)


def cmd_info(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    info = d.info
    print(f"Model:     {info.manufacturer} {info.model}")
    print(f"Android:   {info.android_version} (SDK {info.sdk})")
    print(f"Display:   {info.display_width}x{info.display_height} ({info.display_dpi}dpi)")


def cmd_screenshot(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    filename = args.output or "screenshot.png"
    d.screenshot(filename)
    print(f"Saved to {filename}")


def cmd_shell(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    result = d.shell(args.command)
    if result.output:
        print(result.output)
    sys.exit(result.exit_code)


def cmd_apps(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    apps = d.app.list(filter=args.filter)
    for app in apps:
        print(f"  {app.package}  {app.label}  v{app.version_name}")


def cmd_notifications(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    notifs = d.notifications.list()
    if not notifs:
        print("No notifications.")
        return
    for n in notifs:
        print(f"  [{n.package}] {n.title}: {n.text}")


def cmd_metrics(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    m = d.metrics.snapshot()
    print(f"CPU:     {m.cpu_percent}%")
    print(f"RAM:     {m.ram_used_mb}/{m.ram_total_mb} MB")
    print(f"Battery: {m.battery_level}% {'(charging)' if m.is_charging else ''}")
    print(f"Temp:    {m.battery_temperature}°C")
    print(f"Network: {m.network_type} rx:{m.network_rx_rate} tx:{m.network_tx_rate} B/s")


def main():
    parser = argparse.ArgumentParser(
        prog="droidlink",
        description="droidlink - Python bridge for Android device control",
    )
    parser.add_argument("--version", action="version", version=f"droidlink {__version__}")
    parser.add_argument("-s", "--serial", help="ADB device serial")
    parser.add_argument("-w", "--wifi", help="WiFi device IP address")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("devices", help="List connected devices")
    sub.add_parser("ping", help="Check agent connectivity")
    sub.add_parser("info", help="Show device info")

    ss = sub.add_parser("screenshot", help="Take a screenshot")
    ss.add_argument("-o", "--output", help="Output filename (default: screenshot.png)")

    sh = sub.add_parser("shell", help="Run a shell command")
    sh.add_argument("command", help="Shell command to execute")

    ap = sub.add_parser("apps", help="List installed apps")
    ap.add_argument("-f", "--filter", default="user", choices=["all", "user", "system"])

    sub.add_parser("notifications", help="List recent notifications")
    sub.add_parser("metrics", help="Show device metrics")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    handlers = {
        "devices": cmd_devices,
        "ping": cmd_ping,
        "info": cmd_info,
        "screenshot": cmd_screenshot,
        "shell": cmd_shell,
        "apps": cmd_apps,
        "notifications": cmd_notifications,
        "metrics": cmd_metrics,
    }

    handler = handlers.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
