# dataops — Spark 4 data engineering monorepo

Dev environment: **Spark 4.1.3**, **Python 3.12**, **Java 17**, all defined in `.devcontainer/Dockerfile`.

## Layout
```
.devcontainer/        Dockerfile + devcontainer.json
libs/common/          shared Spark session factory, transforms (importable by every pipeline)
src/pipelines/<area>/<etl>/   one package `pipelines`; jobs grouped by subject area
tests/<area>/         tests mirroring src/pipelines
data/                 local raw/processed data (processed is git-ignored)
```
The root project is the single `pipelines` package; it is also a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) whose members are the dirs under `libs/*`.

## Use
Open in VS Code → "Reopen in Container", then:
```
make test           # all tests
make run-example    # run pipelines.examples.example_etl
make lint
```
Spark UI on :4040 while a job runs.

## Add a pipeline
Create `src/pipelines/<area>/<etl>/` (with `__init__.py` and `job.py`) and a test under `tests/<area>/`. Run with `python -m pipelines.<area>.<etl>.job`.
