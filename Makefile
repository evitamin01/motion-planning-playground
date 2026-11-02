# Convenience targets. They use the project-local Conda environment (./.conda) when it
# exists and fall back to the active Python otherwise, so activation is optional.

ifeq ($(OS),Windows_NT)
  ENV_PY := .conda/python.exe
  ENV_RUFF := .conda/Scripts/ruff.exe
else
  ENV_PY := .conda/bin/python
  ENV_RUFF := .conda/bin/ruff
endif

PYTHON ?= $(if $(wildcard $(ENV_PY)),$(ENV_PY),python)
# conda-forge ships ruff as a standalone binary (no `python -m ruff`).
RUFF ?= $(if $(wildcard $(ENV_RUFF)),$(ENV_RUFF),ruff)
RUN := $(PYTHON) -m
PORT ?= 8000
SOURCES := src tests examples

.PHONY: help env update-env serve test test-fast coverage lint format typecheck check-js check screenshots clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env:  ## Create the Conda environment in ./.conda
	conda env create --prefix ./.conda --file environment.yml

update-env:  ## Update ./.conda after dependency changes
	conda env update --prefix ./.conda --file environment.yml --prune

serve:  ## Start the web UI (PORT=8000)
	$(RUN) mpplay serve --port $(PORT)

test:  ## Run the test suite
	$(RUN) pytest

test-fast:  ## Run the tests, skipping slow ones
	$(RUN) pytest -m "not slow"

coverage:  ## Run the tests with a coverage report
	$(RUN) pytest --cov=mpplay --cov-report=term-missing

lint:  ## Lint with ruff
	$(RUFF) check $(SOURCES)
	$(RUFF) format --check $(SOURCES)

format:  ## Format and auto-fix with ruff
	$(RUFF) format $(SOURCES)
	$(RUFF) check --fix $(SOURCES)

typecheck:  ## Type-check with mypy
	$(RUN) mypy

check-js:  ## Syntax-check the web UI scripts (needs Node.js)
	@for f in src/mpplay/web/js/*.js src/mpplay/web/js/ui/*.js; do node --check "$$f" || exit 1; done
	@echo "JavaScript OK"

check: lint typecheck test  ## Everything CI runs (except check-js)

screenshots:  ## Regenerate docs/images (needs Chrome/Chromium)
	PYTHON=$(PYTHON) bash scripts/screenshots.sh

clean:  ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -not -path "./.conda/*" -prune -exec rm -rf {} +
