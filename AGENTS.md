# AGENTS.md

This file gives AI coding agents the context they need to work in this repository.

## Project

Motion Planning Playground (`mpplay`) is an interactive platform for exploring,
visualizing and comparing 2D motion planning algorithms. It has a Python core, a FastAPI
server and a vanilla-JavaScript browser UI. See `docs/architecture.md` for the design.

## Environment and commands

- The development environment is a Conda prefix environment at `./.conda` (created from
  `environment.yml`). Call tools through it without activating: `./.conda/bin/python`,
  `./.conda/bin/pytest`, `./.conda/bin/ruff`, `./.conda/bin/mypy`. Do not install packages
  globally or into other environments.
- `make check` runs ruff (lint and format check), mypy and pytest; all must pass.
  `make check-js` syntax-checks the UI scripts (needs Node.js).
- `pytest -m "not slow"` skips slow tests; the full suite takes about 20 seconds.
- `./.conda/bin/mpplay serve --no-browser --port 8765` starts the app; `.claude/launch.json`
  defines the same command for preview tooling.
- `bash scripts/screenshots.sh` regenerates `docs/images/` with headless Chrome.

## Layout

- `src/mpplay/` is the core library: `geometry.py`, `collision.py`, `environment.py`,
  `grid.py`, `trace.py`, `params.py`, `runner.py`, `metrics.py`, `postprocess.py`,
  `benchmark.py`, `scenarios.py`, `cli.py` and `viz.py`.
- `src/mpplay/planners/` holds the registry and base class (`base.py`), grid planners
  (`grid_search.py`), sampling planners (`sampling.py`) and `potential_field.py`.
- `src/mpplay/server/app.py` is the FastAPI app (JSON API + static UI).
- `src/mpplay/web/` is the UI: `index.html`, `css/app.css`, and `js/` (`app.js` is the
  controller; `ui/` holds the panels). It uses ES modules with no build step.
- `tests/` is the pytest suite, `examples/` contains runnable examples (tested by
  `tests/test_examples.py`), and `docs/` the guides and reference.

## Conventions

- Python 3.10+, full type hints, ruff with line length 100, docstrings on public APIs.
- Planners subclass `Planner`, use `@register_planner`, declare `Params` with `param(...)`,
  take all randomness from `rng`, and report progress through the `Recorder`. They never
  time themselves or validate their own paths; `runner.run_planner` does both.
- Keep the core independent of the server and UI. New features should be usable from
  Python and the CLI, not only from the browser.
- UI code: no frameworks or bundlers. Colors come from CSS custom properties (light and
  dark themes); the canvas reads them via `themeColors()`.
- Collision checking must stay exact (`CollisionChecker`), and grid rasterization must
  stay conservative. Tests in `tests/test_collision.py` and `tests/test_grid.py` encode
  these invariants.
- Update `CHANGELOG.md` (Unreleased) and the relevant docs with user-facing changes.
