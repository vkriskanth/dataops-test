#!/usr/bin/env bash
# Fetch a previously uploaded artifact by name, from whichever run produced it.
#
# This is the heart of build-once-promote-many: QAT and PRD never check out and rebuild,
# they download the exact bytes that were built on merge. Requires GH_TOKEN and
# `actions: read` permission.
#
#   fetch_artifact.sh dist-2026.10.14.1 dist
#   fetch_artifact.sh qat-2026.10.14.1 records
set -euo pipefail

NAME="${1:?usage: fetch_artifact.sh <artifact-name> [dest] [--optional]}"
DEST="${2:-.}"
OPTIONAL="${3:-}"

echo "Resolving artifact ${NAME}"
RUN_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts?per_page=100&name=${NAME}" \
  --jq '.artifacts | sort_by(.created_at) | reverse | .[0].workflow_run.id // empty')

if [ -z "${RUN_ID}" ]; then
  if [ "${OPTIONAL}" = "--optional" ]; then
    echo "::warning::no artifact named ${NAME} (continuing, caller treats this as absent)"
    exit 0
  fi
  echo "::error::no artifact named ${NAME}. Was it ever produced, or has it expired?"
  exit 1
fi

echo "Found in run ${RUN_ID}; downloading to ${DEST}/"
mkdir -p "${DEST}"
gh run download "${RUN_ID}" --name "${NAME}" --dir "${DEST}"
ls -la "${DEST}"
