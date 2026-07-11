#!/usr/bin/env python
"""Dead-link checker for the DeviceKit documentation suite (plan 16 phase 5).

Scans the docs tree and the repo-root docs for markdown links, resolves relative file
targets, and verifies in-file anchors against GitHub-style heading slugs. External links
(http/https/mailto) and links inside fenced code blocks are skipped.

Usage:
    python scripts/check_docs_links.py        # exits 1 if any link is broken

Scope: the user-facing docs (docs/** except docs/plans/) plus README.md, ROADMAP.md, and
prompture_integration.md. The numbered plan docs under docs/plans/ are internal design
history and are not policed here; they remain valid link *targets*.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LINK_RE = re.compile(r'(?<!\!)\[[^\]]+\]\(([^)]+)\)')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
FENCE_RE = re.compile(r'```.*?```', re.S)

ROOT_DOCS = ('README.md', 'ROADMAP.md', 'prompture_integration.md')


def slugify(text):
    """Approximate GitHub's heading-slug algorithm (lowercase, strip punctuation, spaces
    -> hyphens; existing/double hyphens preserved)."""
    text = text.strip().lower().replace('`', '')
    text = re.sub(r'[^a-z0-9 \-]', '', text)
    return text.replace(' ', '-')


def heading_slugs(path):
    """The set of anchors a file exposes, with GitHub's -1/-2 dedup suffixes."""
    counts = {}
    try:
        with open(path, encoding='utf-8') as fh:
            in_fence = False
            for line in fh:
                if line.lstrip().startswith('```'):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                m = HEADING_RE.match(line)
                if m:
                    s = slugify(m.group(2))
                    counts[s] = counts.get(s, 0) + 1
    except OSError:
        return set()
    anchors = set()
    for s, n in counts.items():
        anchors.add(s)
        for i in range(1, n):
            anchors.add(f"{s}-{i}")
    return anchors


def collect_sources():
    sources = [os.path.join(ROOT, f) for f in ROOT_DOCS if os.path.exists(os.path.join(ROOT, f))]
    for base, dirs, files in os.walk(os.path.join(ROOT, 'docs')):
        if 'plans' in base.split(os.sep):
            dirs[:] = []
            continue
        for f in files:
            if f.endswith('.md'):
                sources.append(os.path.join(base, f))
    return sources


def check():
    problems = []
    for path in collect_sources():
        with open(path, encoding='utf-8') as fh:
            text = FENCE_RE.sub('', fh.read())
        rel_dir = os.path.dirname(path)
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            here = os.path.relpath(path, ROOT)
            if target.startswith('#'):
                if slugify(target[1:]) not in heading_slugs(path):
                    problems.append(f"{here} -> {target}  (missing anchor)")
                continue
            filepart, _, anchor = target.partition('#')
            tgt = os.path.normpath(os.path.join(rel_dir, filepart))
            if not os.path.exists(tgt):
                problems.append(f"{here} -> {target}  (missing file)")
            elif anchor and slugify(anchor) not in heading_slugs(tgt):
                problems.append(f"{here} -> {target}  (missing anchor)")
    return problems


def main():
    sources = collect_sources()
    problems = check()
    if problems:
        print(f"[x] {len(problems)} broken link(s):")
        for p in sorted(set(problems)):
            print("    " + p)
        return 1
    print(f"[ok] scanned {len(sources)} files, no broken links.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
