"""Dump the Flask route table (rules + methods, excluding endpoint names).

Used to prove the API Blueprint refactor (plan 02) is a pure reorganization: the
snapshot must be byte-identical before and after. Endpoint names intentionally change
(blueprint namespacing) so they are excluded.

Usage:
    python tools/route_snapshot.py > /tmp/routes_after.txt
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask


def dump(app):
    lines = []
    for rule in app.url_map.iter_rules():
        methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        lines.append(f"{rule.rule}  [{','.join(methods)}]")
    return "\n".join(sorted(lines))


def main():
    from devicekit import Client

    client = Client()
    app = client.build_app()
    print(dump(app))


if __name__ == "__main__":
    main()
