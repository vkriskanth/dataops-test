"""Tests for turning CAB-approved PR numbers into a deployable pipeline set.

The release branch artifact holds every PR merged into it. These tests pin down which
subsets can be deployed by scoping alone, and which cannot be separated at all.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"{name}_script", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{name}_script"] = module
    spec.loader.exec_module(module)
    return module


resolve = _load("resolve_prs")

ALL = ["dev_1_pipeline", "dev_2_pipeline", "dev_3_pipeline", "examples.example_etl"]

# The four-developer release: three own pipelines, one shared-code change.
RELEASE = {
    101: ["src/pipelines/dev_1_pipeline/job.py"],
    102: ["src/pipelines/dev_2_pipeline/job.py"],
    103: ["src/pipelines/dev_3_pipeline/job.py"],
    104: ["libs/common/src/common/transforms.py"],
}


def test_all_approved_deploys_everything():
    result = resolve.plan(RELEASE, {101, 102, 103, 104}, ALL)
    assert result["errors"] == []
    assert result["deploy"] == ALL
    assert result["held_back"] == []


def test_rejecting_one_pipeline_pr_holds_only_that_pipeline():
    """CAB rejects dev_2. Everything else still ships from the same artifact."""
    result = resolve.plan(RELEASE, {101, 103, 104}, ALL)
    assert result["errors"] == []
    assert result["deploy"] == ["dev_1_pipeline", "dev_3_pipeline", "examples.example_etl"]
    assert result["held_back"] == ["dev_2_pipeline"]


def test_approved_shared_change_reaches_all_but_held_back_pipelines():
    result = resolve.plan(RELEASE, {101, 103, 104}, ALL)
    assert "shared code" in " ".join(result["warnings"])
    assert "dev_2_pipeline" not in result["deploy"]


def test_rejecting_the_shared_change_is_impossible():
    """A rejected libs/ change is already in the artifact -- scoping cannot exclude it."""
    result = resolve.plan(RELEASE, {101, 102, 103}, ALL)
    assert result["errors"]
    assert "shared code" in result["errors"][0]
    assert "[104]" in result["errors"][0]


def test_two_prs_on_the_same_pipeline_cannot_be_separated():
    release = {
        201: ["src/pipelines/dev_1_pipeline/job.py"],
        202: ["src/pipelines/dev_1_pipeline/transform.py"],
    }
    result = resolve.plan(release, {201}, ALL)
    assert result["errors"]
    assert "BOTH an approved and a rejected PR" in result["errors"][0]
    assert "dev_1_pipeline" in result["errors"][0]


def test_only_pipeline_prs_no_shared_change():
    release = {k: v for k, v in RELEASE.items() if k != 104}
    result = resolve.plan(release, {101, 103}, ALL)
    assert result["errors"] == []
    assert result["deploy"] == ["dev_1_pipeline", "dev_3_pipeline"]
    assert result["basis"].startswith("pipelines directly touched")


def test_nothing_approved_deploys_nothing():
    release = {k: v for k, v in RELEASE.items() if k != 104}
    result = resolve.plan(release, set(), ALL)
    assert result["deploy"] == []


def test_per_pr_breakdown_marks_scope_and_approval():
    result = resolve.plan(RELEASE, {101}, ALL)
    assert result["per_pr"][101]["approved"] is True
    assert result["per_pr"][101]["blanket"] is False
    assert result["per_pr"][104]["blanket"] is True
    assert result["per_pr"][102]["approved"] is False


def test_pr_number_extraction_handles_both_merge_styles():
    assert resolve.MERGE_PATTERNS[0].search("Merge pull request #101 from me/branch")
    assert resolve.MERGE_PATTERNS[1].search("Add dev_1_pipeline (#101)")
