#!/usr/bin/env python3
"""Add provenance headers to repository-owned Python files using Git history.

Run from a complete local clone on the intended branch:
    python scripts/add_python_file_headers.py
Preview first:
    python scripts/add_python_file_headers.py --check

Creation dates reflect the earliest Git addition found with --follow, not
necessarily the date the source was originally written.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {".git", ".venv", "venv", "node_modules", "__pycache__", "out", "data"}
ATTRIBUTION = re.compile(
    r"(?im)^\\s*(?:@author\\s*:|author\\s*:|created(?:\\s+on)?\\s*:|copyright\\b|spdx-license-identifier\\s*:)"
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def first_added_date(path: Path) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    # --follow tracks renames, including the recent SELiRA test relocation.
    result = git("log", "--follow", "--diff-filter=A", "--format=%as", "--", rel)
    if result:
        return result.splitlines()[-1]
    # A file may predate the available Git history or have no detectable add.
    return None


def header_position(source: str) -> int:
    """Keep shebang and PEP 263 encoding comments at the top."""
    lines = source.splitlines(keepends=True)
    i = 0
    if lines and lines[0].startswith("#!"):
        i = 1
    if i < min(2, len(lines)) and re.search(r"coding[:=]\\s*[-\\w.]+", lines[i]):
        i += 1
    return sum(len(line) for line in lines[:i])


def insert_header(source: str, created: str) -> str | None:
    if ATTRIBUTION.search(source[:1600]):
        return None
    prefix_end = header_position(source)
    prefix, body = source[:prefix_end], source[prefix_end:]
    header = f'"""Created: {created}\\nAuthor: Harish\\n"""\\n\\n'
    # Insert before the module docstring, preserving its content and the
    # legality of subsequent from __future__ imports.
    candidate = prefix + header + body
    try:
        ast.parse(candidate)
        ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report changes without writing")
    args = parser.parse_args()
    changed, skipped = 0, 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in EXCLUDE for part in path.relative_to(ROOT).parts):
            continue
        try:
            source = tokenize.open(path).read()
            created = first_added_date(path)
        except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
            print(f"SKIP {path.relative_to(ROOT)}: {exc}")
            skipped += 1
            continue
        if not created:
            print(f"SKIP {path.relative_to(ROOT)}: no reliable Git creation date")
            skipped += 1
            continue
        updated = insert_header(source, created)
        if updated is None:
            skipped += 1
            continue
        print(f"{'WOULD UPDATE' if args.check else 'UPDATE'} {path.relative_to(ROOT)} ({created})")
        changed += 1
        if not args.check:
            with tokenize.open(path) as f:
                encoding = f.encoding
            path.write_bytes(updated.encode(encoding))
    print(f"Files {'eligible' if args.check else 'updated'}: {changed}; skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
