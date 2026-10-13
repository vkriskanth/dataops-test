#!/usr/bin/env python3
"""The deployment seam -- currently a dummy.

Everything around it (scoping, gating, versioning, promotion) is real and lives in the
workflows. To make deploys real, replace the body of ``deploy_pipeline`` with a call to
your orchestrator -- Databricks Jobs API, Airflow DAG sync, EMR step submit, a Helm
upgrade, whatever you run. Nothing else in the release machinery needs to change.

Two invariants this script exists to preserve:

  * it is handed a *version that already exists*, never a source tree to build from, so
    what reaches prd is bit-identical to what QA validated
  * it deploys exactly the pipelines it is told to, so a release can promote 99 pipelines
    while leaving the one CAB rejected on its previous version
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ENVIRONMENTS = ("dev", "qat", "prd")


def deploy_pipeline(pipeline: str, version: str, env: str, namespace: str) -> dict[str, str]:
    """Register one pipeline at one version in one environment.

    REPLACE ME. A real implementation would, for example, upsert a job definition whose
    entry point is ``python -m pipelines.<area>.<name>.job`` with libraries pinned to
    ``dataops==<version>`` and ``common==<version>``, and leave the schedule untouched so
    deployment and activation stay separate.
    """
    # Pipeline ids are already dotted module paths, flat ("sales_agg") or nested
    # ("examples.example_etl"), so no splitting is needed for either layout.
    module = f"pipelines.{pipeline}.job"
    prefix = f"{namespace}-" if namespace else ""
    job_name = f"{env}-{prefix}{pipeline.replace('.', '-')}"

    print(f"  [{env}] {pipeline}")
    print(f"        job name   : {job_name}")
    print(f"        entry point: python -m {module}")
    print(f"        libraries  : dataops=={version}, common=={version}")
    print(f"        namespace  : {namespace or '(none)'}")
    print("        schedule   : unchanged (activation is a separate config change)")

    return {"pipeline": pipeline, "job_name": job_name, "module": module}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, choices=ENVIRONMENTS)
    ap.add_argument("--version", required=True)
    ap.add_argument("--pipelines", required=True, help="comma-separated pipeline ids")
    ap.add_argument("--namespace", default="", help="dev only; isolates one developer")
    ap.add_argument("--blanket", default="false")
    ap.add_argument("--change-record", default="")
    ap.add_argument("--record", default="", help="write a deployment record to this path")
    args = ap.parse_args()

    pipelines = [p.strip() for p in args.pipelines.split(",") if p.strip()]
    if not pipelines:
        print("::warning::nothing to deploy -- no pipelines in scope")
        return 0

    blanket = args.blanket.lower() == "true"
    scope = "BLANKET (shared code changed)" if blanket else "TARGETED"

    print(f"Deploying {args.version} to {args.env.upper()} -- {scope}")
    if args.change_record:
        print(f"Change record: {args.change_record}")
    print(f"{len(pipelines)} pipeline(s) in scope\n")

    deployed = [deploy_pipeline(p, args.version, args.env, args.namespace) for p in pipelines]

    record = {
        "env": args.env,
        "version": args.version,
        "blanket": blanket,
        "namespace": args.namespace,
        "change_record": args.change_record,
        "deployed_at": datetime.now(UTC).isoformat(),
        "deployed_by": os.environ.get("GITHUB_ACTOR", "local"),
        "run_url": (
            f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}"
            f"/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        ),
        "pipelines": deployed,
    }

    if args.record:
        path = Path(args.record)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"\nDeployment record -> {path}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Deployed `{args.version}` to **{args.env.upper()}**\n\n")
            if args.change_record:
                fh.write(f"Change record: `{args.change_record}`\n\n")
            fh.write(f"Scope: {scope}\n\n")
            fh.write("| Pipeline | Job |\n|---|---|\n")
            for item in deployed:
                fh.write(f"| `{item['pipeline']}` | `{item['job_name']}` |\n")

    print(f"\nDone -- {len(deployed)} pipeline(s) deployed to {args.env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
