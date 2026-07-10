"""CLI tool for devicekit."""

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


def cmd_files(args):
    from . import connect, connect_wifi
    d = connect_wifi(args.wifi) if args.wifi else connect(serial=args.serial)
    sub = args.files_command

    if sub == "list":
        path = args.path or "/sdcard"
        entries = d.files.list(path)
        for f in entries:
            kind = "D" if f.is_dir else "F"
            size = f"{f.size:>10}" if not f.is_dir else "         -"
            print(f"  [{kind}] {size}  {f.name}")

    elif sub == "search":
        result = d.files.search(args.query, path=args.path or "/sdcard", limit=args.limit)
        for item in result.get("results", []):
            kind = "D" if item["is_dir"] else "F"
            print(f"  [{kind}] {item['path']}")
        print(f"  ({result.get('count', 0)} results)")

    elif sub == "upload":
        import os
        size = os.path.getsize(args.local)

        def progress(sent, total):
            pct = int(sent / total * 100) if total else 0
            print(f"\r  Uploading... {pct}%", end="", flush=True)

        result = d.files.upload(args.local, args.remote, progress_callback=progress)
        print(f"\n  Uploaded to {result.get('path')} ({result.get('size')} bytes)")

    elif sub == "pull":
        def progress(downloaded, total):
            if total:
                pct = int(downloaded / total * 100)
                print(f"\r  Downloading... {pct}%", end="", flush=True)

        d.files.pull(args.remote, args.local, progress_callback=progress)
        print(f"\n  Saved to {args.local}")

    else:
        print("Unknown files subcommand. Use: list, search, upload, pull")


def main():
    parser = argparse.ArgumentParser(
        prog="devicekit",
        description="devicekit - Python bridge for Android device control",
    )
    parser.add_argument("--version", action="version", version=f"devicekit {__version__}")
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

    # Files command group
    files_parser = sub.add_parser("files", help="File operations")
    files_sub = files_parser.add_subparsers(dest="files_command")

    fs_list = files_sub.add_parser("list", help="List files in directory")
    fs_list.add_argument("-p", "--path", default="/sdcard", help="Directory path")

    fs_search = files_sub.add_parser("search", help="Search files by name")
    fs_search.add_argument("query", help="Search query (substring match)")
    fs_search.add_argument("-p", "--path", default="/sdcard", help="Root directory")
    fs_search.add_argument("-l", "--limit", type=int, default=50, help="Max results")

    fs_upload = files_sub.add_parser("upload", help="Upload file to device")
    fs_upload.add_argument("local", help="Local file path")
    fs_upload.add_argument("remote", help="Remote device path")

    fs_pull = files_sub.add_parser("pull", help="Pull file from device")
    fs_pull.add_argument("remote", help="Remote device path")
    fs_pull.add_argument("local", help="Local destination path")

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
        "files": cmd_files,
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
