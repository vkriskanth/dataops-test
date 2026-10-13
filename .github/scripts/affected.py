#!/usr/bin/env python3
"""Work out which pipelines a change set affects.

The rule, and the only rule:

  * changes confined to ``src/pipelines/<area>/<name>/`` affect just those pipelines
  * anything shared -- ``libs/``, the root pyproject, ``uv.lock``, CI, the devcontainer
    -- is a *blanket* change and affects every pipeline

Blast radius drives both deploy scope and (via CODEOWNERS) review requirements, so this
one function is the thing every workflow agrees on.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PIPELINE_ROOT = Path("src/pipelines")
TEST_ROOT = Path("tests")

# Paths that affect nothing deployable.
IGNORED_SUFFIXES = (".md",)
IGNORED_PREFIXES = ("data/", ".vscode/", ".devcontainer/devcontainer.json")


def discover() -> list[str]:
    """Every pipeline in the tree, as dotted ids.

    Both layouts are recognised, so a pipeline is never misread as a shared change:

      src/pipelines/<area>/<name>/job.py  ->  "<area>.<name>"   (README convention)
      src/pipelines/<name>/job.py         ->  "<name>"          (flat)
    """
    ids = {job.parent.name for job in PIPELINE_ROOT.glob("*/job.py")}
    ids |= {
        f"{job.parent.parent.name}.{job.parent.name}" for job in PIPELINE_ROOT.glob("*/*/job.py")
    }
    return sorted(ids)


def _rev_exists(rev: str) -> bool:
    if not rev or set(rev) == {"0"}:
        return False
    return (
        subprocess.run(["git", "rev-parse", "--verify", rev], capture_output=True).returncode == 0
    )


def changed_files(base: str, head: str) -> list[str] | None:
    """Files changed between two revs, or None if the range can't be resolved."""
    if not _rev_exists(base) or not _rev_exists(head):
        return None
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line]


def _ignored(path: str) -> bool:
    return path.endswith(IGNORED_SUFFIXES) or path.startswith(IGNORED_PREFIXES)


def classify(files: list[str], all_pipelines: list[str]) -> tuple[bool, list[str]]:
    """Return (blanket, pipelines)."""
    touched: set[str] = set()
    for path in files:
        if _ignored(path):
            continue
        parts = Path(path).parts
        if len(parts) >= 4 and parts[:2] == ("src", "pipelines"):
            # Prefer the nested id, fall back to the flat one.
            nested = f"{parts[2]}.{parts[3]}" if len(parts) >= 5 else None
            if nested and nested in all_pipelines:
                touched.add(nested)
                continue
            if parts[2] in all_pipelines:
                touched.add(parts[2])
                continue
            # A pipeline that no longer exists, or an unexpected layout. Be conservative.
            return True, all_pipelines
        # Anything else is shared: libs/, pyproject, uv.lock, CI, src/pipelines/__init__.py
        return True, all_pipelines
    return False, sorted(touched)


def pytest_paths(blanket: bool, pipelines: list[str]) -> list[str]:
    """Test dirs to run. ``libs`` always runs -- shared code underpins every pipeline."""
    if blanket:
        return ["libs", "tests"]
    areas = sorted({pid.split(".", 1)[0] for pid in pipelines})
    paths = ["libs"]
    paths.extend(str(TEST_ROOT / area) for area in areas if (TEST_ROOT / area).is_dir())
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="base rev; unresolvable means blanket")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument(
        "--override",
        default="auto",
        help="'auto' to detect, 'all' to force blanket, or comma-separated pipeline ids",
    )
    ap.add_argument("--github-output", action="store_true", help="also write to $GITHUB_OUTPUT")
    args = ap.parse_args()

    all_pipelines = discover()
    if not all_pipelines:
        print("::error::no pipelines found under src/pipelines/<area>/<name>/job.py")
        return 1

    override = args.override.strip()
    if override == "all":
        blanket, pipelines, why = True, all_pipelines, "forced (override=all)"
    elif override and override != "auto":
        requested = [p.strip() for p in override.split(",") if p.strip()]
        unknown = sorted(set(requested) - set(all_pipelines))
        if unknown:
            print(f"::error::unknown pipeline ids: {', '.join(unknown)}")
            print(f"known: {', '.join(all_pipelines)}")
            return 1
        blanket, pipelines, why = False, sorted(requested), "explicit override"
    else:
        files = changed_files(args.base, args.head)
        if files is None:
            blanket, pipelines = True, all_pipelines
            why = f"could not resolve {args.base}...{args.head}; assuming blanket"
        else:
            blanket, pipelines = classify(files, all_pipelines)
            why = f"{len(files)} changed file(s) between {args.base[:8]} and {args.head[:8]}"

    tests = pytest_paths(blanket, pipelines)
    result = {
        "blanket": blanket,
        "pipelines": pipelines,
        "pytest_paths": tests,
        "all_pipelines": all_pipelines,
        "reason": why,
    }

    # stdout stays pure JSON so callers can pipe it; annotations go to stderr.
    print(json.dumps(result, indent=2))
    print(f"::notice::{'BLANKET' if blanket else 'TARGETED'} -- {why}", file=sys.stderr)

    out = os.environ.get("GITHUB_OUTPUT")
    if args.github_output and out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"blanket={'true' if blanket else 'false'}\n")
            fh.write(f"pipelines={','.join(pipelines)}\n")
            fh.write(f"pytest_paths={' '.join(tests)}\n")
            fh.write(f"count={len(pipelines)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
