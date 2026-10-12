.PHONY: install test typecheck lint ci fmt run-example jupyter

install:
	uv sync --all-packages --inexact --group dev

test:
	pytest

typecheck:
	pyrefly check

lint:
	ruff check . && ruff format --check .
	pylint src libs/common/src tests libs/common/tests

ci: lint typecheck test

fmt:
	ruff check --fix . && ruff format .

run-example:
	python -m pipelines.examples.example_etl.job

jupyter:
	jupyter lab --ip=0.0.0.0 --no-browser
