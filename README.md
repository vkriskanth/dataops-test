# dataops — Spark 4 data engineering monorepo

Dev environment: **Spark 4.1.3**, **Python 3.12**, **Java 17**, all defined in `.devcontainer/Dockerfile`.

## Layout
```
.devcontainer/        Dockerfile + devcontainer.json
libs/common/          shared Spark session factory, transforms (importable by every pipeline)
pipelines/<name>/     one package per pipeline, each with its own pyproject + tests
data/                 local raw/processed data (processed is git-ignored)
```
It is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): every dir under `libs/*` and `pipelines/*` is a member.

## Use
Open in VS Code → "Reopen in Container", then:
```
make test           # all tests
make run-example    # run pipelines/example_etl
make lint
```
Spark UI on :4040 while a job runs.

## Add a pipeline
Copy `pipelines/example_etl`, rename the package, add it to `[tool.uv.sources]` and the `dev` group in the root `pyproject.toml`, then `make install`.
