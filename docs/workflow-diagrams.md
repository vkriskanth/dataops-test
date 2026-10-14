# Development and release flow

Five views of the same process, each answering one question. GitHub renders these
diagrams inline; VS Code previews them with the Markdown preview pane.

Prose details live in [release-process.md](release-process.md).

---

## 1. The whole path, start to finish

One artifact is built on merge to `main` and the **same bytes** are promoted onward.
Nothing after the build ever recompiles from source.

```mermaid
flowchart LR
    subgraph loop["Developer loop — any day, no coordination"]
        direction TB
        FB["feature branch"]
        DPR["draft PR"]
        DEVENV["dev<br/>namespace pr-N"]
        FB --> DPR
        DPR -. "manual dispatch" .-> DEVENV
    end

    loop --> CI["CI<br/>lint, types, targeted tests"]
    CI --> REV{"peer review"}
    REV -- approved --> MAIN["main<br/>always releasable"]

    MAIN --> BUILD["build-release<br/>wheel 2026.10.14.N"]
    BUILD --> QATC["QAT<br/>continuous from main"]

    MAIN -. "Monday 14:00" .-> CUT["cut-release<br/>freeze release/thu-date"]
    CUT --> RC["release candidate<br/>one artifact"]
    RC --> QATR["QAT<br/>candidate under test"]
    QATR --> QA{"QA sign-off<br/>per pipeline"}
    QA --> CAB{"CAB<br/>Thursday"}
    CAB -- "approved subset" --> PROD["PRD<br/>scoped promote + tag"]
    CAB -- rejected --> DORM["stays in main<br/>dormant"]
    DORM -. "later train" .-> CAB
```

The two QAT boxes are the same environment. It tracks `main` continuously so problems
surface hours after merging, and holds the frozen candidate during release week.

---

## 2. Weekly cadence

Developers work on their own schedule. Only the release track is dated.

```mermaid
gantt
    title Release week
    dateFormat YYYY-MM-DD
    axisFormat %a
    todayMarker off

    section Developers
    Merge to main, QAT refreshes continuously :active, d1, 2026-10-12, 11d

    section Release track
    Cut RC and freeze          :milestone, m1, 2026-10-19, 0d
    QA validates the candidate :crit, qa, 2026-10-19, 3d
    One change record raised   :milestone, m2, 2026-10-21, 0d
    CAB review                 :milestone, m3, 2026-10-22, 0d
    Production deploy          :milestone, m4, 2026-10-22, 0d
    Buffer, only if re-cut     :buf, 2026-10-23, 1d
```

A change merged Tuesday waits for the following Monday's cut and ships about nine days
later. That is the cost of weekly CAB, not a limitation of the pipeline.

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
    participant M as main
    participant Q as QAT
    participant R as Release manager
    participant P as PRD

    Note over D,Q: 10/14 — each merge refreshes QAT within minutes
    D->>M: 09:00  dev_2 merges
    M->>Q: deploy — TARGETED
    D->>M: 10:00  dev_1 merges
    M->>Q: deploy — TARGETED
    D->>M: 13:00  dev_3 merges
    M->>Q: deploy — TARGETED
    D->>M: 16:00  dev_4 merges libs/
    M->>Q: deploy — BLANKET
    Note over Q: full suite re-runs;<br/>dev_1 and dev_3 sign-offs refreshed<br/>against the final combined state

    R->>R: Mon — cut RC, freeze, build once
    Q->>R: QA signs off per pipeline
    R->>P: Thu after CAB — promote approved subset
    Note over P: same bytes QA validated
```

Every developer still gets same-day feedback. Nobody waits for a QAT slot, because QAT is
never a resource one PR holds.

---

## 5. One artifact, selective deployment

How CAB rejects a single item without anyone cherry-picking.

```mermaid
flowchart TD
    A["artifact 2026.10.14.1<br/>built once from main"] --> Q["QAT — all four pipelines<br/>validated together"]
    Q --> CAB{"CAB Thursday"}

    CAB -- approved --> OK["dev_1, dev_3, common"]
    CAB -- rejected --> NO["dev_2"]

    OK --> DEP["deploy-prod<br/>version = 2026.10.14.1<br/>pipelines = dev_1, dev_3, examples"]
    DEP --> LIVE["PRD runs 2026.10.14.1"]

    NO --> HOLD["dev_2 keeps its<br/>previously deployed version"]
    HOLD --> STAY["code stays merged in main,<br/>dormant — never deployed"]
    STAY --> NEXT["rides a later train:<br/>same artifact, no rebuild,<br/>no cherry-pick"]

    style DEP fill:#14532d,stroke:#16a34a,color:#f0fdf4
    style NEXT fill:#1e3a5f,stroke:#3b82f6,color:#eff6ff
```

The approved list scopes **what gets deployed**, never what gets built. That is the whole
difference between this and assembling code on release day — the artifact promoted to
production is byte-identical to the one QA tested.

Per-pipeline `common==<version>` pinning is what makes the exclusion real: `dev_2` keeps
running against its old shared code rather than silently picking up the new one.

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
