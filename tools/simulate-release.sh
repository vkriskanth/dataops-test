#!/usr/bin/env bash
# Replay the four-developer release cycle locally, end to end, in a throwaway clone.
# Nothing touches your real repo or GitHub.
#
# Feature branches merge into the RELEASE branch; main receives the release only at the
# end. CAB approval is given as PR numbers, which resolve to a deployable pipeline set.
#
#   PR #101  dev_1  src/pipelines/dev_1_pipeline      -> targeted
#   PR #102  dev_2  src/pipelines/dev_2_pipeline      -> targeted, REJECTED by CAB
#   PR #103  dev_3  src/pipelines/dev_3_pipeline      -> targeted
#   PR #104  dev_4  libs/common/.../transforms.py     -> BLANKET (stales the above)
#
# Usage: tools/simulate-release.sh [--keep]
set -euo pipefail

SRC=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
WORK=$(mktemp -d)
KEEP=${1:-}
VERSION="2026.10.14.1"

cleanup() {
  if [ "$KEEP" = "--keep" ]; then
    echo "Workspace kept at: $WORK"
  else
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

hr() { printf '\n\033[1m%s\033[0m\n' "=== $* ==="; }
note() { printf '  %s\n' "$*"; }

scope_of() { # -> "BLANKET|TARGETED  <comma-separated ids>"
  python3 .github/scripts/affected.py --base "$1" --head HEAD 2>/dev/null |
    python3 -c "
import json,sys
d=json.load(sys.stdin)
print(('BLANKET ' if d['blanket'] else 'TARGETED'), ','.join(d['pipelines']))"
}

hr "Setting up a throwaway clone"
git clone -q "$SRC" "$WORK/repo"
cd "$WORK/repo"
git checkout -q -B main
# Pick up any uncommitted work from the source tree, so we test current code.
for d in .github/scripts libs src tests; do
  rm -rf "$d" && mkdir -p "$(dirname "$d")" && cp -r "$SRC/$d" "$d"
done
cp "$SRC/pyproject.toml" "$SRC/uv.lock" .
git add -A && git commit -q -m "Baseline" --allow-empty
git config user.email sim@example.com && git config user.name "Release Sim"
BASE=$(git rev-parse HEAD)
note "baseline commit $(git rev-parse --short HEAD)"
note "pipelines at baseline: $(python3 .github/scripts/affected.py --override all 2>/dev/null |
  python3 -c "import json,sys;print(','.join(json.load(sys.stdin)['all_pipelines']))")"

hr "10/12 - open-release creates the cycle's branch from main"
git checkout -q -b release/2026-10-16 "$BASE"
git push -q origin release/2026-10-16 2>/dev/null || true
REL=$(git rev-parse HEAD)
note "release/2026-10-16 opened at $(git rev-parse --short HEAD)"
note "main stays at $(git rev-parse --short "$BASE") until the end of the cycle"

hr "10/13 - four developers branch from the RELEASE branch"
for n in 1 2 3; do
  git checkout -q -b "feature/dev_${n}" "$REL"
  mkdir -p "src/pipelines/dev_${n}_pipeline"
  : >"src/pipelines/dev_${n}_pipeline/__init__.py"
  cat >"src/pipelines/dev_${n}_pipeline/job.py" <<EOF
from common import config


def main() -> None:
    cfg = config.load()
    print(cfg.output("processed/dev_${n}"))
EOF
  git add -A && git commit -q -m "Add dev_${n}_pipeline (#10${n})"
  note "feature/dev_${n}  $(scope_of "$REL")"
done

git checkout -q -b feature/dev_4_common "$REL"
cat >>libs/common/src/common/transforms.py <<'EOF'


def common_utility(value: str) -> str:
    return value.strip().lower()
EOF
git add -A && git commit -q -m "Add common_utility (#104)"
note "feature/dev_4_common  $(scope_of "$REL")  <-- shared code"

hr "10/14 - PRs merge into the RELEASE branch; QAT follows it"
declare -a ORDER=("feature/dev_2 09:00" "feature/dev_1 10:00" "feature/dev_3 13:00" "feature/dev_4_common 16:00")
git checkout -q release/2026-10-16
for entry in "${ORDER[@]}"; do
  set -- $entry
  branch=$1 time=$2
  before=$(git rev-parse HEAD)
  git merge -q --no-ff -m "Merge pull request #10${branch##*_} from me/${branch}" "$branch" 2>/dev/null ||
    git merge -q --no-ff -m "Merge ${branch}" "$branch"
  printf '  %s  merged %-22s -> QAT now %s\n' "$time" "$branch" "$(scope_of "$before")"
done
note "main is still at $(git rev-parse --short "$BASE") - untouched all cycle"

hr "The step your original flow was missing"
note "dev_4's shared change landed LAST, at 16:00."
note "dev_1 signed off at 10:00 and dev_3 at 13:00 - both against the OLD common."
note "deploy-qat.yml sees blanket=true and re-runs the FULL suite, so those"
note "stale sign-offs are refreshed against the final combined state."
uv run --project "$SRC" pytest -q "$SRC/libs" "$SRC/tests" 2>&1 | tail -2 || note "(test run skipped)"

hr "10/14 18:00 - build ONE artifact from the release branch"
ALL_P=$(python3 .github/scripts/affected.py --override all 2>/dev/null |
  python3 -c "import json,sys;print(','.join(json.load(sys.stdin)['all_pipelines']))")
note "release contains: $ALL_P"
python3 .github/scripts/stamp_version.py "$VERSION" | sed 's/^/  /'
mkdir -p dist records
ALL_P="$ALL_P" VERSION="$VERSION" python3 - <<'PY'
import json, os, subprocess
from datetime import UTC, datetime, timedelta

sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
info = {
    "version": os.environ["VERSION"],
    "channel": "rc",
    "sha": sha,
    "ref": "release/2026-10-16",
    # backdated so the 24h soak gate passes, as it would by Thursday
    "built_at": (datetime.now(UTC) - timedelta(hours=30)).isoformat(),
    "blanket": True,
    "pipelines": os.environ["ALL_P"].split(","),
    "recent_prs": ["104", "103", "102", "101"],
}
json.dump(info, open("dist/build-info.json", "w"), indent=2)
PY
note "build-info.json written (soak backdated 30h)"

hr "10/14-15 - deploy the candidate to QAT"
python3 .github/scripts/deploy.py --env qat --version "$VERSION" \
  --pipelines "$ALL_P" --blanket true --record records/qat.json | sed 's/^/  /'

hr "10/15 CAB - approves #101 #103 #104, REJECTS #102 (dev_2)"
# CAB gives PR numbers. resolve_prs maps them to pipelines, offline here via --files-json.
cat >prs.json <<'EOF'
{
  "101": ["src/pipelines/dev_1_pipeline/job.py"],
  "102": ["src/pipelines/dev_2_pipeline/job.py"],
  "103": ["src/pipelines/dev_3_pipeline/job.py"],
  "104": ["libs/common/src/common/transforms.py"]
}
EOF
if python3 .github/scripts/resolve_prs.py --approved 101,103,104 \
  --files-json prs.json 2>&1 | sed 's/^/  /'; then
  note "PR resolution: OK"
else
  note "PR resolution: BLOCKED"
fi
APPROVED=$(cat approved_pipelines.txt)
echo
python3 .github/scripts/verify_release.py \
  --build-info dist/build-info.json \
  --qat-record records/qat.json \
  --version "$VERSION" \
  --pipelines "$APPROVED" 2>&1 | sed 's/^/  /' || note "gate FAILED"

hr "What happens if CAB rejects the SHARED-code PR instead"
python3 .github/scripts/resolve_prs.py --approved 101,102,103 \
  --files-json prs.json 2>&1 | grep -E '::error|blocking' | sed 's/^/  /' || true
note "refused, correctly - that code is in the artifact and cannot be excluded"

hr "10/16 - promote the SAME artifact, scoped to the approved PRs"
python3 .github/scripts/deploy.py --env prd --version "$VERSION" \
  --pipelines "$APPROVED" --blanket true \
  --change-record "CHG0041234" --record records/prd.json | sed 's/^/  /'

hr "10/16 - close-release merges the release into main and tags it"
git checkout -q main
git merge -q --no-ff release/2026-10-16 -m "Release ${VERSION} (CHG0041234)"
git tag -a "v${VERSION}" -m "Release ${VERSION}" 2>/dev/null || true
note "main now at $(git rev-parse --short HEAD), tagged v${VERSION}"
note "main contains the whole release, including rejected #102"

hr "Result"
note "PRD running $VERSION for: $APPROVED"
note "dev_2_pipeline: NOT deployed - still on its previous version"
note "#102's code IS in main, dormant, and is picked up by the next release."
note "Nothing was cherry-picked. Nothing was rebuilt. No branch surgery."
