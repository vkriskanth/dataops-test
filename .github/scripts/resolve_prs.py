#!/usr/bin/env python3
"""Turn a list of CAB-approved PR numbers into a deployable pipeline set.

The release branch artifact contains *every* PR merged into it. CAB may approve only
some. This script answers: given the approved PR numbers, which pipelines can we deploy
from that one artifact without shipping unapproved code?

It scopes the DEPLOY, never the build. Nothing is cherry-picked and nothing is rebuilt,
so what reaches production is byte-identical to what QA validated.

Two situations make selection impossible, and both are hard stops:

  * a rejected PR changed shared code (libs/, uv.lock, ...). That code is in the
    artifact and every deployed pipeline will run it, so excluding it is a fiction.
  * an approved and a rejected PR both touched the same pipeline. The artifact holds
    both changes; deploying one without the other cannot be done by scoping.

In either case the honest options are to slip the release or re-cut without the
rejected PR -- which is what the Friday buffer exists for.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from affected import classify, discover  # noqa: E402

MERGE_PATTERNS = (
    re.compile(r"^Merge pull request #(\d+) "),  # merge commit
    re.compile(r"\(#(\d+)\)$"),  # squash commit
)


def prs_in_range(base: str, head: str) -> list[int]:
    """PR numbers merged between two revs, newest first."""
    out = subprocess.run(
        ["git", "log", "--pretty=%s", f"{base}..{head}"],
        capture_output=True,
        text=True,
    )
    found: list[int] = []
    for line in out.stdout.splitlines():
        for pattern in MERGE_PATTERNS:
            match = pattern.search(line.strip())
            if match:
                num = int(match.group(1))
                if num not in found:
                    found.append(num)
                break
    return found


def pr_files(repo: str, number: int) -> list[str]:
    """Files a PR changed, via the GitHub API."""
    out = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{number}/files",
            "--paginate",
            "--jq",
            ".[].filename",
        ],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"::error::could not read files for PR #{number}: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line]


def pr_base(repo: str, number: int) -> tuple[str, str]:
    """(baseRefName, state) for a PR, so we can confirm it is really in this release."""
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{number}", "--jq", '.base.ref + " " + .state'],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return ("", "")
    parts = out.stdout.strip().split()
    return (parts[0], parts[1]) if len(parts) == 2 else ("", "")


def plan(
    files_by_pr: dict[int, list[str]],
    approved: set[int],
    all_pipelines: list[str],
) -> dict:
    """Decide what to deploy. Pure function -- no I/O, so it is unit tested."""
    per_pr: dict[int, dict] = {}
    approved_direct: set[str] = set()
    rejected_direct: set[str] = set()
    blanket_approved: list[int] = []
    blanket_rejected: list[int] = []

    for number in sorted(files_by_pr):
        blanket, pipelines = classify(files_by_pr[number], all_pipelines)
        is_approved = number in approved
        per_pr[number] = {
            "approved": is_approved,
            "blanket": blanket,
            "pipelines": pipelines,
        }
        if blanket:
            (blanket_approved if is_approved else blanket_rejected).append(number)
            # A blanket PR's own pipeline list is "everything", which would swamp the
            # overlap check. Its effect is handled explicitly below.
            continue
        (approved_direct if is_approved else rejected_direct).update(pipelines)

    errors: list[str] = []
    warnings: list[str] = []

    if blanket_rejected:
        errors.append(
            f"rejected PR(s) {blanket_rejected} changed shared code, which is already in "
            f"the artifact and will run under every deployed pipeline. Excluding them by "
            f"scoping is not possible -- slip the release or re-cut without them."
        )

    overlap = sorted(approved_direct & rejected_direct)
    if overlap:
        errors.append(
            f"pipeline(s) {overlap} were touched by BOTH an approved and a rejected PR. "
            f"The artifact holds both changes, so they cannot be separated by scoping."
        )

    # Shared code that WAS approved should reach every pipeline except the held-back ones.
    if blanket_approved:
        deploy = set(all_pipelines) - rejected_direct
        basis = f"approved shared change in PR(s) {blanket_approved}, minus held-back pipelines"
        warnings.append(
            f"PR(s) {blanket_approved} changed shared code. Pipelines held back "
            f"({sorted(rejected_direct) or 'none'}) keep their previous common version -- "
            f"confirm each pins common==<previous>."
        )
    else:
        deploy = approved_direct - rejected_direct
        basis = "pipelines directly touched by the approved PRs"

    return {
        "deploy": sorted(deploy),
        "held_back": sorted(rejected_direct - deploy),
        "basis": basis,
        "per_pr": per_pr,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved", required=True, help="comma-separated approved PR numbers")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--release-branch", default="", help="confirm PRs targeted this branch")
    ap.add_argument("--base", default="main", help="rev the release branch diverged from")
    ap.add_argument("--head", default="HEAD", help="release branch tip")
    ap.add_argument(
        "--files-json",
        default="",
        help='offline: {"101": ["path", ...]} instead of calling the GitHub API',
    )
    ap.add_argument("--github-output", action="store_true")
    args = ap.parse_args()

    approved = {int(p.strip()) for p in args.approved.split(",") if p.strip()}
    all_pipelines = discover()

    if args.files_json:
        raw = json.loads(Path(args.files_json).read_text(encoding="utf-8"))
        files_by_pr = {int(k): v for k, v in raw.items()}
    else:
        if not args.repo:
            print("::error::--repo or GITHUB_REPOSITORY is required")
            return 1
        numbers = prs_in_range(args.base, args.head)
        if not numbers:
            print(f"::error::no PRs found between {args.base} and {args.head}")
            return 1
        print(f"PRs in this release: {numbers}")
        files_by_pr = {}
        for number in numbers:
            if args.release_branch:
                base_ref, state = pr_base(args.repo, number)
                if base_ref and base_ref != args.release_branch:
                    print(f"::warning::PR #{number} targeted {base_ref}, not {args.release_branch}")
                if state and state.upper() not in ("MERGED", "CLOSED"):
                    print(f"::warning::PR #{number} state is {state}")
            files_by_pr[number] = pr_files(args.repo, number)

    unknown = approved - set(files_by_pr)
    if unknown:
        print(f"::error::approved PR(s) {sorted(unknown)} are not in this release")
        print(f"release contains: {sorted(files_by_pr)}")
        return 1

    result = plan(files_by_pr, approved, all_pipelines)

    print("\n=== Per-PR breakdown ===")
    for number, info in sorted(result["per_pr"].items()):
        mark = "APPROVED" if info["approved"] else "REJECTED"
        scope = "BLANKET " if info["blanket"] else "targeted"
        print(f"  #{number:<6} {mark:<9} {scope}  {', '.join(info['pipelines']) or '-'}")

    print("\n=== Plan ===")
    print(f"  basis    : {result['basis']}")
    print(f"  deploy   : {', '.join(result['deploy']) or '(nothing)'}")
    print(f"  held back: {', '.join(result['held_back']) or '(none)'}")

    for message in result["warnings"]:
        print(f"::warning::{message}")
    for message in result["errors"]:
        print(f"::error::{message}")

    if result["errors"]:
        print(f"\n{len(result['errors'])} blocking problem(s) -- cannot scope this release.")
        return 1

    if not result["deploy"]:
        print("::error::no pipelines left to deploy")
        return 1

    Path("approved_pipelines.txt").write_text(",".join(result["deploy"]), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if args.github_output and out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"pipelines={','.join(result['deploy'])}\n")
            fh.write(f"held_back={','.join(result['held_back'])}\n")
    print(f"\nOK -- {len(result['deploy'])} pipeline(s) to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
