.PHONY: install test lint fmt run-example jupyter

install:
	uv sync --all-packages --inexact

test:
	pytest

lint:
	ruff check . && ruff format --check .

fmt:
	ruff check --fix . && ruff format .

run-example:
	python -m example_etl.job

jupyter:
	jupyter lab --ip=0.0.0.0 --no-browser
