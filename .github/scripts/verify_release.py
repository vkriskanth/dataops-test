#!/usr/bin/env python3
"""Gate checks run immediately before a production deploy.

These are the checks that make "promote an artifact" meaningfully different from
"merge and build": they prove the exact version being promoted is the one that sat in
QAT, that it has soaked long enough, and that the pipelines CAB approved are actually
in it. Any failure here stops the deploy before anything is touched.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def fail(msg: str) -> None:
    print(f"::error::{msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-info", required=True)
    ap.add_argument("--qat-record", default="", help="QAT deployment record for this version")
    ap.add_argument("--version", required=True)
    ap.add_argument("--pipelines", required=True, help="CAB-approved ids, or 'all'")
    ap.add_argument("--min-soak-hours", type=float, default=24.0)
    ap.add_argument("--skip-soak-check", default="false")
    args = ap.parse_args()

    info = json.loads(Path(args.build_info).read_text(encoding="utf-8"))
    errors: list[str] = []

    # 1. The artifact is the one we think it is.
    if info.get("version") != args.version:
        errors.append(f"build-info version {info.get('version')!r} != requested {args.version!r}")

    built = info.get("pipelines") or []
    if not built:
        errors.append("build-info lists no pipelines")

    # 2. It actually reached QAT. Promotion without prior QAT exposure is not a release.
    if args.qat_record:
        qat = json.loads(Path(args.qat_record).read_text(encoding="utf-8"))
        if qat.get("version") != args.version:
            errors.append(f"QAT record is for {qat.get('version')!r}, not {args.version!r}")
        if qat.get("env") != "qat":
            errors.append(f"QAT record env is {qat.get('env')!r}")
        print(f"QAT deployment confirmed at {qat.get('deployed_at')}")
    else:
        errors.append(f"no QAT deployment record found for {args.version} -- it never reached QAT")

    # 3. Minimum soak. Policy, not per-change date negotiation.
    if args.skip_soak_check.lower() == "true":
        print("::warning::soak check skipped -- expected only for a hotfix")
    else:
        built_at = info.get("built_at")
        if not built_at:
            errors.append("build-info has no built_at timestamp")
        else:
            age = datetime.now(UTC) - datetime.fromisoformat(built_at)
            needed = timedelta(hours=args.min_soak_hours)
            print(f"Soak: {age.total_seconds() / 3600:.1f}h (minimum {args.min_soak_hours}h)")
            if age < needed:
                errors.append(
                    f"only soaked {age.total_seconds() / 3600:.1f}h of the required "
                    f"{args.min_soak_hours}h -- slip the train or use skip_soak_check"
                )

    # 4. The approved set is a subset of what was built and validated. This is the check
    #    that makes CAB selectivity safe: you can deploy fewer pipelines than the
    #    artifact contains, but never one the artifact does not have.
    requested = args.pipelines.strip()
    if requested == "all":
        approved = sorted(built)
        print(f"Deploying all {len(approved)} pipeline(s) in the release")
    else:
        approved = sorted({p.strip() for p in requested.split(",") if p.strip()})
        if not approved:
            errors.append("no pipelines requested")
        extra = sorted(set(approved) - set(built))
        if extra:
            errors.append(
                f"not in release {args.version}: {', '.join(extra)} -- "
                f"release contains: {', '.join(sorted(built))}"
            )
        held = sorted(set(built) - set(approved))
        if held:
            print(f"Held back (not CAB-approved): {', '.join(held)}")
            print("  these keep running their previously deployed version")

    if info.get("blanket") and requested != "all":
        print(
            "::warning::this release contains a change to shared code (libs/), so excluding "
            "individual pipelines may not isolate them -- confirm each held-back pipeline "
            "pins its previous common version"
        )

    for err in errors:
        fail(err)
    if errors:
        print(f"\n{len(errors)} gate check(s) failed -- deploy aborted")
        return 1

    Path("approved_pipelines.txt").write_text(",".join(approved), encoding="utf-8")
    print(f"\nAll gate checks passed. Promoting {args.version} ({len(approved)} pipelines).")
    print(f"Commit: {info.get('sha', 'unknown')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
