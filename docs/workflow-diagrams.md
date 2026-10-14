# Development and release flow

Five views of the same process, each answering one question. GitHub renders these
diagrams inline; VS Code previews them with the Markdown preview pane.

Prose details live in [release-process.md](release-process.md).

---

## 1. The whole path, start to finish

Feature work merges into the **release branch**. `main` receives only a completed,
CAB-approved release, so `main` records what is in production. One artifact is built per
merge, and the **same bytes** are promoted onward — nothing after the build recompiles.

```mermaid
flowchart LR
    OPEN["open-release<br/>Monday<br/>release/thu-date"] --> REL

    subgraph loop["Developer loop — any day during the cycle"]
        direction TB
        FB["feature branch<br/>off the release branch"]
        DPR["draft PR<br/>base = release branch"]
        DEVENV["dev<br/>namespace pr-N"]
        FB --> DPR
        DPR -. "manual dispatch" .-> DEVENV
    end

    loop --> CI["CI<br/>lint, types, targeted tests"]
    CI --> REV{"peer review"}
    REV -- approved --> REL["release branch<br/>integration"]

    REL --> BUILD["build-release<br/>wheel 2026.10.14.N"]
    BUILD --> QAT["QAT<br/>refreshed every merge"]
    BUILD --> MANI["tracking PR to main<br/>= CAB manifest"]

    QAT --> QA{"QA sign-off<br/>per pipeline"}
    QA --> CAB{"CAB<br/>Thursday"}

    CAB -- "approved PR numbers" --> PROD["deploy-prod<br/>scoped, same bytes"]
    CAB -- "rejected" --> HELD["pipeline held back<br/>keeps previous version"]

    PROD --> CLOSE["close-release<br/>merge to main + tag"]
    HELD --> CLOSE
    CLOSE --> MAIN["main<br/>= what is in production"]
    MAIN -. "next cycle" .-> OPEN
```

Only **one** release branch is open at a time. `open-release` refuses to create a second
one, because two open releases diverge and you resolve that by hand.

Held-back code still merges to `main` as part of the release — dormant, never deployed,
and eligible for the next release with no cherry-picking.

---

## 2. Weekly cadence

Developers work on their own schedule. Only the release track is dated.

```mermaid
gantt
    title One release cycle
    dateFormat YYYY-MM-DD
    axisFormat %a
    todayMarker off

    section Branch
    Open release branch        :milestone, m0, 2026-10-19, 0d
    Feature PRs merge into it  :active, d1, 2026-10-19, 3d
    Merge to main + tag        :milestone, m5, 2026-10-22, 0d

    section Validation
    QAT refreshed every merge  :q1, 2026-10-19, 3d
    QA sign-off per pipeline   :crit, qa, 2026-10-21, 2d

    section Approval
    One change record raised   :milestone, m2, 2026-10-21, 0d
    CAB review                 :milestone, m3, 2026-10-22, 0d
    Production deploy          :milestone, m4, 2026-10-22, 0d
    Buffer, only if re-cut     :buf, 2026-10-23, 1d
```

Work that misses the cycle waits for the next release branch. Because `main` only moves
at the end, the next cycle's branch must be opened **after** the previous one merges —
`open-release` enforces this by refusing to create a second open release branch.

---

## 3. Blast radius — one rule, used everywhere

Computed once in [`affected.py`](../.github/scripts/affected.py). It drives how much gets
tested, how much gets deployed, and (via `CODEOWNERS`) who must review.

```mermaid
flowchart TD
    START["files changed"] --> Q{"confined to<br/>src/pipelines/&lt;area&gt;/&lt;name&gt;/ ?"}
    Q -- yes --> T["TARGETED"]
    Q -- "no — libs/, pyproject,<br/>uv.lock, CI, devcontainer" --> B["BLANKET"]

    T --> T1["deploy only those pipelines"]
    T --> T2["run libs + tests/&lt;area&gt;"]
    T --> T3["peer review"]

    B --> B1["deploy every pipeline"]
    B --> B2["run the full suite"]
    B --> B3["platform-team review"]
    B --> B4["invalidates every earlier<br/>per-pipeline sign-off"]

    style B4 fill:#7f1d1d,stroke:#dc2626,color:#fef2f2
```

`B4` is the one most hand-rolled processes miss: a shared change landing **last** silently
staled every sign-off that came before it. `deploy-qat.yml` re-runs everything when it
sees `blanket=true`.

---

## 4. A real day: four developers, staggered merges

```mermaid
sequenceDiagram
    autonumber
    participant D as Developers
    participant R as release/2026-10-16
    participant Q as QAT
    participant C as CAB
    participant P as PRD
    participant M as main

    Note over R: 10/12 — open-release creates the branch from main

    Note over D,Q: 10/14 — each merge rebuilds the candidate and refreshes QAT
    D->>R: 09:00  PR #102 dev_2 merges
    R->>Q: deploy — TARGETED
    D->>R: 10:00  PR #101 dev_1 merges
    R->>Q: deploy — TARGETED
    D->>R: 13:00  PR #103 dev_3 merges
    R->>Q: deploy — TARGETED
    D->>R: 16:00  PR #104 dev_4 merges libs/
    R->>Q: deploy — BLANKET
    Note over Q: full suite re-runs;<br/>#101 and #103 sign-offs refreshed<br/>against the final combined state

    Q->>C: 10/15 QA signs off per pipeline
    Note over C: approves #101 #103 #104<br/>rejects #102
    C->>P: 10/16 deploy-prod approved_prs=101,103,104
    Note over P: dev_2_pipeline held back,<br/>keeps its previous version
    P->>M: close-release — merge + tag v2026.10.14.1
    Note over M: #102's code is in main,<br/>dormant, rides the next release
```

Every developer still gets same-day feedback. Nobody waits for a QAT slot, because QAT is
never a resource one PR holds.

Note step 8: dev_4's shared change lands **last**, which stales the sign-offs from steps
4 and 6. The blanket revalidation is what makes staggered per-PR testing safe.

---

## 5. Approved PR numbers to a deployed pipeline set

You hand `deploy-prod` the PR numbers CAB approved. It resolves them to pipelines and
scopes the deploy — no cherry-picking, no rebuild.

```mermaid
flowchart TD
    A["artifact 2026.10.14.1<br/>contains PRs #101 #102 #103 #104"] --> Q["QAT — validated together"]
    Q --> CAB{"CAB Thursday"}
    CAB --> IN["approved_prs = 101,103,104"]

    IN --> RES["resolve_prs.py<br/>PR numbers → changed files → pipelines"]
    RES --> CHK{"can scoping<br/>express this?"}

    CHK -- yes --> DEP["deploy-prod<br/>pipelines = dev_1, dev_3, examples"]
    DEP --> LIVE["PRD runs 2026.10.14.1"]
    DEP --> HOLD["dev_2_pipeline held back —<br/>keeps its previous version"]

    CHK -- "rejected PR touched libs/" --> X1["REFUSE<br/>shared code is in the artifact<br/>and runs under every pipeline"]
    CHK -- "approved + rejected PR<br/>touched the same pipeline" --> X2["REFUSE<br/>artifact holds both changes"]

    X1 --> OPT["slip the release,<br/>or re-cut without it<br/>(Friday buffer)"]
    X2 --> OPT

    style DEP fill:#14532d,stroke:#16a34a,color:#f0fdf4
    style X1 fill:#7f1d1d,stroke:#dc2626,color:#fef2f2
    style X2 fill:#7f1d1d,stroke:#dc2626,color:#fef2f2
```

The approved list scopes **what gets deployed**, never what gets built. That is the whole
difference between this and assembling code on release day — the artifact promoted to
production is byte-identical to the one QA tested.

Per-pipeline `common==<version>` pinning is what makes a held-back pipeline real: `dev_2`
keeps running against its old shared code instead of silently picking up the new one.

The two red paths are not pessimism — they are the cases where "deploy only the approved
PRs" is not a thing that can be done without building something nobody tested. The
workflow stops instead of pretending.

---

## Rollback

```mermaid
flowchart LR
    NOW["PRD on 2026.10.14.1"] -- "problem found" --> RR["re-run deploy-prod<br/>version = 2026.10.7.3"]
    RR --> BACK["PRD on 2026.10.7.3"]
    BACK -. "artifact still exists,<br/>bit-identical" .-> BACK
```

Code rollback is a single workflow re-run. **Data is not** — a pipeline that already
overwrote good output with bad is not recovered by redeploying code. Partition writes and
validate to a staging path before publishing.
