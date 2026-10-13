#!/usr/bin/env python3
"""Stamp one build version across every workspace package before building.

Both wheels carry the same version, so a deploy can pin ``common==<version>`` next to
``dataops==<version>`` and each pipeline ships a self-contained bundle. That pinning is
what lets a release exclude one pipeline without disturbing the others.
"""

import argparse
import re
import sys
from pathlib import Path

VERSION_LINE = re.compile(r'^version\s*=\s*"[^"]*"$', re.MULTILINE)


def targets() -> list[Path]:
    return [Path("pyproject.toml"), *sorted(Path("libs").glob("*/pyproject.toml"))]


def stamp(path: Path, version: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = VERSION_LINE.subn(f'version = "{version}"', text, count=1)
    if count != 1:
        raise SystemExit(f"{path}: expected one top-level version line, matched {count}")
    path.write_text(new, encoding="utf-8")
    print(f"  {path} -> {version}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="e.g. 2026.10.13.42")
    args = ap.parse_args()
    print(f"Stamping version {args.version}")
    for path in targets():
        stamp(path, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
