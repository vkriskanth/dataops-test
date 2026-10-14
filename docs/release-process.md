# Release process

Three environments, **one artifact**. A wheel is built once per merge into the release
branch, and the same bytes are promoted to QAT and then production. Nothing in the
deploy path ever checks out source and rebuilds, so what QA validated is what ships.

Environments differ only by injected config (`DATAOPS_*` env vars, see
`libs/common/src/common/config.py`). There is no environment-specific code and no
environment branch.

## Branch model

Feature branches merge into the **release branch**, never into `main`.

```
feature/*  ──PR──▶  release/<date>  ──after production──▶  main + tag
```

`main` receives code only from `close-release`, and only after a production deploy
record exists. So `main` is a record of what has been through CAB and reached
production, not a staging area.

Consequences worth knowing:

- **Branch from the release branch**, not `main`, for work in the current cycle. `main`
  does not have this cycle's work until the end.
- **Only one release branch open at a time.** `open-release` refuses to create a second
  one. Two open releases do not contain each other's work, and you resolve that by hand.
- **Held-back code still merges to `main`** as part of the release. It is dormant — never
  deployed — and is picked up by the next release automatically. Surgically removing it
  would diverge `main` from the artifact that was actually tested.

## Weekly cadence

| When | What | Who |
|---|---|---|
| **Mon 13:00 UTC** | `Open release` creates `release/<thu-date>` from `main` | Automated |
| Any day in cycle | Feature branch off the release branch, PR into it, `Deploy to dev` freely | Developer |
| Any day in cycle | PR reviewed and merged. Candidate rebuilt, QAT refreshed, tracking PR updated | Developer + reviewer |
| Mon–Wed | QA validates the candidate, signing off **per pipeline** | QA |
| Wed EOD | One change record raised, using the tracking PR body as the manifest | Release manager |
| **Thu (after CAB)** | `Deploy to production` with the version + **approved PR numbers** | Release manager |
| Thu/Fri | `Close release` merges the release into `main` and tags it | Release manager |
| Fri | Buffer, only if Thursday needed a re-cut | Release manager |

## Workflows

| Workflow | Trigger | Notes |
|---|---|---|
| `ci.yml` | PR, push to `main`/`release/**`, merge queue | Targeted tests on PRs, full suite everywhere else |
| `deploy-dev.yml` | Manual, from your branch | Namespaced per PR. No review needed |
| `open-release.yml` | Monday cron, or manual | Creates the cycle's release branch; refuses if one is open |
| `build-release.yml` | Push to `release/**` | The only place a wheel is built. Also keeps the tracking PR current |
| `deploy-qat.yml` | Called by `build-release`, or manual | Downloads an artifact; never builds |
| `deploy-prod.yml` | Manual, `prd` environment approval | Promotes an existing version, scoped by approved PR numbers |
| `close-release.yml` | Manual, after production | Merges the release into `main` and tags. Refuses without a prod record |

## Selecting which PRs go to production

`deploy-prod` takes `approved_prs` — the PR numbers CAB approved:

```bash
gh workflow run deploy-prod.yml \
  -f version=2026.10.14.1 \
  -f approved_prs=101,103,104 \
  -f change_record=CHG0041234
```

`.github/scripts/resolve_prs.py` maps each PR to the files it changed, then to the
pipelines those files affect, and deploys only those. **It scopes the deploy, never the
build** — the artifact is untouched, so what ships is byte-identical to the candidate QA
validated. A rejected PR's pipeline keeps its previously deployed version.

Two situations cannot be expressed by scoping, and the workflow refuses rather than
shipping something untested:

| Situation | Why it cannot work | What to do |
|---|---|---|
| A **rejected** PR changed `libs/`, `uv.lock` or the root `pyproject.toml` | That code is in the artifact and runs under every deployed pipeline. Excluding it is a fiction | Slip the release, or re-cut without it |
| An **approved** and a **rejected** PR touched the same pipeline | The artifact holds both changes; they cannot be separated by choosing what to deploy | Slip, re-cut, or get the second PR approved |

The Friday buffer exists for the re-cut case. A re-cut owes a fresh validation cycle,
because the new combination was never in QAT.

As an escape hatch, `-f pipelines=<ids>` bypasses PR resolution and names pipelines
directly. Use it for hotfixes; `approved_prs` is the auditable path because it ties the
deploy to the CAB record.

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

The release branch is the integration point: all feature work for the cycle merges into
it, and every merge rebuilds the candidate and refreshes QAT.

Three rules keep that safe:

1. **Nothing merges after CAB.** Once the change record is raised, the branch is closed
   to new work. A merge after CAB means CAB approved a manifest that no longer matches
   the artifact. If something must go in, raise it with CAB or hold it for next cycle.
2. **A late merge restarts the clock.** Each merge produces a new version, so any
   sign-off against the previous one is stale. The 24h soak gate in
   `verify_release.py` enforces this — a last-minute merge will fail it, by design.
3. **One release branch open at a time**, enforced by `open-release`.

Work that misses the cycle waits for the next release branch. The cost of squeezing it
in is the one thing this design is built to prevent: approving one artifact and shipping
another.

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
