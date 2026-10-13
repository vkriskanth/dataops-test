"""Tests for the blast-radius rule that gates every deploy.

Modelled on the four-developer release scenario: three developers each adding their own
pipeline, and one changing shared code. Getting this wrong means either deploying a
pipeline nobody validated, or holding back a blanket change that invalidated everyone
else's sign-off.
"""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "affected.py"


def _load_affected():
    spec = importlib.util.spec_from_file_location("affected_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["affected_script"] = module
    spec.loader.exec_module(module)
    return module


affected = _load_affected()

# dev_1/2/3 use the flat layout from the scenario; example_etl uses the nested one.
ALL = [
    "dev_1_pipeline",
    "dev_2_pipeline",
    "dev_3_pipeline",
    "examples.example_etl",
]


def test_dev_1_touches_only_its_own_pipeline():
    blanket, pipelines = affected.classify(["src/pipelines/dev_1_pipeline/job.py"], ALL)
    assert blanket is False
    assert pipelines == ["dev_1_pipeline"]


def test_each_developer_is_isolated_from_the_others():
    for name in ("dev_1_pipeline", "dev_2_pipeline", "dev_3_pipeline"):
        blanket, pipelines = affected.classify([f"src/pipelines/{name}/job.py"], ALL)
        assert blanket is False
        assert pipelines == [name]


def test_nested_layout_is_recognised():
    blanket, pipelines = affected.classify(["src/pipelines/examples/example_etl/job.py"], ALL)
    assert blanket is False
    assert pipelines == ["examples.example_etl"]


def test_two_pipelines_in_one_change():
    blanket, pipelines = affected.classify(
        ["src/pipelines/dev_1_pipeline/job.py", "src/pipelines/dev_3_pipeline/job.py"], ALL
    )
    assert blanket is False
    assert pipelines == ["dev_1_pipeline", "dev_3_pipeline"]


def test_dev_4_shared_code_is_blanket():
    """A libs/ change invalidates every pipeline-level sign-off that came before it."""
    blanket, pipelines = affected.classify(["libs/common/src/common/common_utility.py"], ALL)
    assert blanket is True
    assert pipelines == ALL


def test_one_shared_file_makes_the_whole_change_blanket():
    blanket, pipelines = affected.classify(["src/pipelines/dev_1_pipeline/job.py", "uv.lock"], ALL)
    assert blanket is True
    assert pipelines == ALL


def test_pipelines_package_init_is_shared():
    blanket, _ = affected.classify(["src/pipelines/__init__.py"], ALL)
    assert blanket is True


def test_unknown_pipeline_dir_is_conservative():
    """A deleted or misnamed pipeline must not silently narrow the deploy."""
    blanket, pipelines = affected.classify(["src/pipelines/ghost_pipeline/job.py"], ALL)
    assert blanket is True
    assert pipelines == ALL


def test_docs_only_change_affects_nothing():
    blanket, pipelines = affected.classify(["README.md", "docs/release-process.md"], ALL)
    assert blanket is False
    assert pipelines == []


def test_targeted_tests_narrow_to_the_right_dirs():
    paths = affected.pytest_paths(False, ["examples.example_etl"])
    assert "libs" in paths
    assert "tests/examples" in paths
    assert "tests" not in paths


def test_blanket_runs_everything():
    assert affected.pytest_paths(True, ALL) == ["libs", "tests"]
