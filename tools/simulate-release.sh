#!/usr/bin/env bash
# Replay the four-developer release scenario locally, end to end, in a throwaway clone.
# Nothing touches your real repo or GitHub.
#
#   dev_1  src/pipelines/dev_1_pipeline      -> targeted
#   dev_2  src/pipelines/dev_2_pipeline      -> targeted, REJECTED by CAB
#   dev_3  src/pipelines/dev_3_pipeline      -> targeted
#   dev_4  libs/common/.../common_utility.py -> BLANKET (invalidates the above)
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

hr "10/13 - four developers branch from main"
for n in 1 2 3; do
  git checkout -q -b "feature/dev_${n}" "$BASE"
  mkdir -p "src/pipelines/dev_${n}_pipeline"
  : >"src/pipelines/dev_${n}_pipeline/__init__.py"
  cat >"src/pipelines/dev_${n}_pipeline/job.py" <<EOF
from common import config


def main() -> None:
    cfg = config.load()
    print(cfg.output("processed/dev_${n}"))
EOF
  git add -A && git commit -q -m "Add dev_${n}_pipeline (#10${n})"
  note "feature/dev_${n}  $(scope_of "$BASE")"
done

git checkout -q -b feature/dev_4_common "$BASE"
cat >>libs/common/src/common/transforms.py <<'EOF'


def common_utility(value: str) -> str:
    return value.strip().lower()
EOF
git add -A && git commit -q -m "Add common_utility (#104)"
note "feature/dev_4_common  $(scope_of "$BASE")  <-- shared code"

hr "10/14 - PRs merge to main through the day; QAT follows main"
declare -a ORDER=("feature/dev_2 09:00" "feature/dev_1 10:00" "feature/dev_3 13:00" "feature/dev_4_common 16:00")
git checkout -q main
for entry in "${ORDER[@]}"; do
  set -- $entry
  branch=$1 time=$2
  before=$(git rev-parse HEAD)
  git merge -q --no-ff -m "Merge ${branch}" "$branch"
  printf '  %s  merged %-22s -> QAT now %s\n' "$time" "$branch" "$(scope_of "$before")"
done

hr "The step your original flow was missing"
note "dev_4's shared change landed LAST, at 16:00."
note "dev_1 signed off at 10:00 and dev_3 at 13:00 - both against the OLD common."
note "deploy-qat.yml sees blanket=true and re-runs the FULL suite, so those"
note "stale sign-offs are refreshed against the final combined state."
uv run --project "$SRC" pytest -q "$SRC/libs" "$SRC/tests" 2>&1 | tail -2 || note "(test run skipped)"

hr "10/14 18:00 - cut the release and build ONE artifact"
git checkout -q -b release/2026-10-16
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

hr "10/15 CAB - C111 approved, C222 REJECTED, C333 approved, C444 approved"
APPROVED=$(python3 -c "
ids = '$ALL_P'.split(',')
print(','.join(i for i in ids if 'dev_2' not in i))")
note "approved pipeline list: $APPROVED"
echo
if python3 .github/scripts/verify_release.py \
  --build-info dist/build-info.json \
  --qat-record records/qat.json \
  --version "$VERSION" \
  --pipelines "$APPROVED" 2>&1 | sed 's/^/  /'; then
  GATE=pass
else
  GATE=fail
fi
note "gate result: $GATE"

hr "10/16 - promote the SAME artifact, scoped to the approved list"
python3 .github/scripts/deploy.py --env prd --version "$VERSION" \
  --pipelines "$(cat approved_pipelines.txt)" --blanket true \
  --change-record "CHG0041234" --record records/prd.json | sed 's/^/  /'

hr "Result"
note "PRD running $VERSION for: $(cat approved_pipelines.txt)"
note "dev_2_pipeline: NOT deployed - still on its previous version"
note "dev_2's code is merged in main, dormant, and rides a later train."
note "Nothing was cherry-picked. Nothing was rebuilt. No branch surgery."
