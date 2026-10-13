# Release process

Three environments, **one artifact**. A wheel is built once on merge to `main` and the
same bytes are promoted to QAT and then production. Nothing in the deploy path ever
checks out source and rebuilds, so what QA validated is what ships.

Environments differ only by injected config (`DATAOPS_*` env vars, see
`libs/common/src/common/config.py`). There is no environment-specific code and no
environment branch.

## Weekly cadence

| When | What | Who |
|---|---|---|
| Any day | Feature branch, draft PR, `Deploy to dev` as often as you like | Developer |
| Any day | PR reviewed, merged to `main`. QAT auto-refreshes within minutes | Developer + reviewer |
| **Mon 14:00 UTC** | `Cut release` freezes `release/<thu-date>`, builds the RC, deploys it to QAT | Automated |
| Mon–Wed | QA validates the RC, signing off **per pipeline** | QA |
| Wed EOD | One change record raised listing every item in the release | Release manager |
| **Thu (after CAB)** | `Deploy to production` with the version + CAB-approved pipeline list | Release manager |
| Fri | Buffer, only if Thursday needed a re-cut | Release manager |

A change merged on Tuesday waits for the following Monday's cut and ships about nine
days later. That is the cost of a weekly CAB cadence; it is not a pipeline limitation.

## Workflows

| Workflow | Trigger | Notes |
|---|---|---|
| `ci.yml` | PR, push to `main`/`release/**`, merge queue | Targeted tests on PRs, full suite everywhere else |
| `deploy-dev.yml` | Manual, from your branch | Namespaced per PR. No review needed |
| `build-release.yml` | Push to `main`, or called | The only place a wheel is built |
| `cut-release.yml` | Monday cron, or manual | Freezes the week's candidate |
| `deploy-qat.yml` | Called by the two above, or manual | Downloads an artifact; never builds |
| `deploy-prod.yml` | Manual, `prd` environment approval | Promotes an existing version |

## Blast radius

One rule, implemented once in `.github/scripts/affected.py` and used by every workflow:

- changes confined to `src/pipelines/<area>/<name>/` → **targeted**, only those pipelines
  are tested and deployed
- anything shared (`libs/`, root `pyproject.toml`, `uv.lock`, CI, devcontainer) →
  **blanket**, every pipeline is tested and deployed

Blast radius drives review requirements too, via `.github/CODEOWNERS`: a pipeline change
needs a peer, a shared change needs the platform team.

**A blanket change invalidates every earlier pipeline-level sign-off**, because pipelines
validated before it ran against a different `common`. `deploy-qat.yml` re-runs the full
suite automatically when it sees one.

## When CAB rejects an item

Work down this list. The first two require no rebuild.

1. **Exclude the pipeline from the deploy** — pass a `pipelines` list to
   `deploy-prod.yml` that omits it. It keeps running its previously deployed version.
   This is why each pipeline pins `common==<version>` rather than sharing one install.
2. **Deactivate by config** — leave the code deployed but unscheduled, or don't cut over
   the output path. `EnvConfig.enabled()` exists for this.
3. **Slip the whole train** to next Monday.
4. **Re-cut without it** — rebuild, re-validate, deploy Friday. Rare by design.

Rejected work **stays merged in `main`**. It is dormant in production because it was
never deployed, and it rides a later train once approved. Nothing is cherry-picked and
nothing is stranded on a branch.

## Release branch rules

The release branch exists for exactly one reason: somewhere to land fixes to the
candidate without pulling in new `main` commits.

> It accepts **fixes to things already on it**. It never accepts new features.

A fix triggers a rebuild and re-validation of the affected pipelines. New work goes to
`main` and waits for the next cut. Without this rule you end up assembling untested
combinations on CAB day, which is the failure mode this whole design exists to avoid.

## Deployment vs activation

Deploying code and releasing behaviour are separate events. If two changes ship on the
same train but need different go-live dates, they both deploy Thursday and activate
independently:

- **new pipeline** — register it unscheduled; enable the schedule on the date
- **additive change** — write the new column from day one; consumers adopt when ready
- **behavioural change** — write to a versioned output path (`.../v2/`), diff against
  the current one, then repoint what "published" means
- **breaking schema change** — expand/contract across several releases

In-code boolean flags are a poor fit for data pipelines (two code paths writing one
dataset). Prefer the output path or the schedule as the switch.

## Rollback

Re-run `deploy-prod.yml` with the previous version. The artifact still exists and is
bit-identical.

Data is harder: a pipeline that already overwrote good output with bad is not recovered
by redeploying code. Partition writes and use `partitionOverwriteMode=dynamic` so a bad
run damages one partition, and validate to a staging path before publishing.

## Branch protection on `main`

- PR required, 1+ approvals, stale approvals dismissed on new commits
- Required status check: `ci`
- Require conversation resolution, require linear history
- Merge queue enabled (`ci.yml` handles the `merge_group` trigger)

## GitHub Environments

| Environment | Protection |
|---|---|
| `dev` | none |
| `qat` | none — auto-deploy on merge is the point |
| `prd` | required reviewers; variables for `DATAOPS_BASE_PATH`, `DATAOPS_FEATURES` |

## Making deploys real

`.github/scripts/deploy.py` is a dummy that prints its plan. Replace the body of
`deploy_pipeline` with a call to your orchestrator — Databricks Jobs API, Airflow DAG
sync, EMR step submit. Everything around it (scoping, gating, versioning, promotion,
tagging) is already real and does not change.
