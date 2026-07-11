#!/usr/bin/env python
"""Reproducible content sha256 for a bundled builtin extension.

Bundled builtins install from ``builtin-extensions/<slug>/`` (a local tree, not a downloaded
zip), so — unlike a remote entry's download checksum — their registry ``sha256`` is a
*content-integrity reference*: sha256 over every tracked file's ``(relpath, length, bytes)``,
files sorted by forward-slash relpath. It is deterministic (independent of filesystem order or
zip timestamps), so anyone can recompute and compare it. Recompute after editing an extension
and update ``devicekit/data/registry_index.json``:

    python scripts/compute_builtin_sha256.py devicekit-browser
    python scripts/compute_builtin_sha256.py --all
"""
import argparse
import hashlib
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
_BUILTINS = os.path.join(_REPO_ROOT, "builtin-extensions")

_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
_SKIP_SUFFIX = (".pyc", ".pyo")


def content_sha256(ext_dir):
    entries = []
    for root, dirs, names in os.walk(ext_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for n in names:
            if n.endswith(_SKIP_SUFFIX):
                continue
            ab = os.path.join(root, n)
            rel = os.path.relpath(ab, ext_dir).replace(os.sep, "/")
            entries.append((rel, ab))
    entries.sort()
    h = hashlib.sha256()
    for rel, ab in entries:
        with open(ab, "rb") as fh:
            data = fh.read()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(data)).encode("ascii"))
        h.update(b"\0")
        h.update(data)
    return h.hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description="Content sha256 of a bundled builtin extension")
    p.add_argument("slug", nargs="?", help="extension slug under builtin-extensions/")
    p.add_argument("--all", action="store_true", help="print for every bundled builtin")
    args = p.parse_args(argv)

    if args.all:
        for name in sorted(os.listdir(_BUILTINS)):
            d = os.path.join(_BUILTINS, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "extension.json")):
                print(f"{content_sha256(d)}  {name}")
        return 0
    if not args.slug:
        p.print_help()
        return 2
    d = os.path.join(_BUILTINS, args.slug)
    if not os.path.isdir(d):
        print(f"[x] No builtin extension at {d}")
        return 1
    print(content_sha256(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
