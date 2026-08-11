#!/usr/bin/env python3
"""Verify every changed-files glob in .github/labels.yml matches a real path.

actions/labeler treats each glob as an opaque string -- nothing checks that
it still points at a file that exists. A rename or directory move can leave
a rule silently dead (it never fires again, and nothing fails), which is
exactly what happened to the `area/image-verify` rule after pkg/images/**
was renamed to pkg/image/** in kyverno/kyverno#15673. This script closes
that gap deterministically: it re-derives, from the current git tree,
whether each rule is still live.

Usage: pip install pyyaml && python3 scripts/verify-labeler-paths.py
   or: make verify-labels
Exit code is non-zero if any pattern matches zero tracked files.
"""

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)
LABELS_FILE = REPO_ROOT / ".github" / "labels.yml"


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a minimatch-style glob (as used by actions/labeler) to a regex.

    Supports the subset actually used in labels.yml: '**' (any depth,
    including zero), '**/' (zero or more leading path segments), '*'
    (within one path segment), and literal segments/characters.
    """
    regex = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern[i : i + 3] == "**/":
            regex.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            regex.append(".*")
            i += 2
        elif pattern[i] == "*":
            regex.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex.append("[^/]")
            i += 1
        else:
            regex.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(regex) + "$")


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
    return out.splitlines()


def iter_rules(labels: dict):
    for label, spec in labels.items():
        if not isinstance(spec, dict):
            continue
        for rule in spec.get("rules") or []:
            for changed_files in rule.get("changed-files") or []:
                for pattern in changed_files.get("any-glob-to-any-file") or []:
                    yield label, pattern


def main() -> int:
    labels = yaml.safe_load(LABELS_FILE.read_text())
    files = tracked_files()

    stale = []
    checked = 0
    for label, pattern in iter_rules(labels):
        checked += 1
        rx = glob_to_regex(pattern)
        if not any(rx.match(f) for f in files):
            stale.append((label, pattern))

    if stale:
        print(f"Checked {checked} glob rules in {LABELS_FILE.relative_to(REPO_ROOT)}.")
        print(f"{len(stale)} match ZERO files in the current tree (stale/dead rule):\n")
        for label, pattern in stale:
            print(f"  {label}: {pattern!r}")
        return 1

    print(f"OK: all {checked} glob rules in {LABELS_FILE.relative_to(REPO_ROOT)} "
          f"match at least one tracked file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
