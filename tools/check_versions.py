#!/usr/bin/env python3
"""매니페스트 세 곳의 version이 CHANGELOG 맨 위 버전과 같은지 본다. --tag vX를 주면 태그도 맞춰 본다.

Usage: python3 tools/check_versions.py [--root DIR] [--tag vX.Y.Z]
Exit 0 when every version agrees, 1 otherwise (each mismatch is printed).
"""
import argparse
import json
import os
import re
import sys

MANIFESTS = (
    (".claude-plugin/plugin.json", lambda d: d["version"]),
    (".claude-plugin/marketplace.json", lambda d: d["plugins"][0]["version"]),
    (".codex-plugin/plugin.json", lambda d: d["version"]),
)
# "## [1.0.0-beta.2] — 2026-11-20"; an "## [Unreleased]" section is skipped.
HEADING = re.compile(r"^## \[([^\]]+)\]")


def changelog_version(root):
    with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as f:
        for line in f:
            m = HEADING.match(line)
            if m and m.group(1).lower() != "unreleased":
                return m.group(1)
    return None


def check(root, tag=None):
    """Return a list of human-readable mismatch lines (empty = all agree)."""
    expected = changelog_version(root)
    if expected is None:
        return ["CHANGELOG.md: no '## [x.y.z]' heading found"]
    errors = []
    for path, get in MANIFESTS:
        with open(os.path.join(root, path), encoding="utf-8") as f:
            got = get(json.load(f))
        if got != expected:
            errors.append(f"{path}: version {got!r} != CHANGELOG {expected!r}")
    if tag is not None and tag != f"v{expected}":
        errors.append(f"tag {tag!r} != 'v' + CHANGELOG {expected!r}")
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p.add_argument("--tag")
    args = p.parse_args(argv)
    errors = check(args.root, args.tag)
    for e in errors:
        print(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") else e)
    if not errors:
        print(f"ok: all versions = {changelog_version(args.root)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
