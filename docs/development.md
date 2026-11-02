# Development setup

This guide explains how to create an isolated, reproducible development environment,
how to run the checks, and how to work on the UI.

## 1. Create the environment

The recommended setup uses [Conda](https://docs.conda.io/) (Miniconda, Miniforge or
Mambaforge all work) with packages from **conda-forge**. The environment is created as a
*prefix environment* inside the project folder (`./.conda`), so it is isolated from your
other environments, does not need a global name, and is removed together with the
project. `.conda/` is ignored by Git.

```bash
git clone https://github.com/evitamin01/motion-planning-playground.git
cd motion-planning-playground
conda env create --prefix ./.conda --file environment.yml
conda activate ./.conda
```

`environment.yml` pins the Python version and lists all runtime and development
dependencies. The last step installs the package itself in *editable* mode
(`pip install --editable .`), so changes to `src/mpplay` take effect immediately without
reinstalling.

Check that everything works:

```bash
mpplay --version
pytest -q
```

If you prefer not to activate the environment, every tool can be called through the
prefix, for example `./.conda/bin/pytest` or `./.conda/bin/mpplay serve` (on Windows:
`.conda\python.exe -m pytest`). The `Makefile` does this automatically.

### Keeping it up to date

After `environment.yml` or `pyproject.toml` changed (for example after a `git pull`):

```bash
conda env update --prefix ./.conda --file environment.yml --prune
```

To start from scratch, delete the folder and create it again:

```bash
conda deactivate
rm -rf .conda
conda env create --prefix ./.conda --file environment.yml
```

### Alternative: plain virtualenv + pip

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The `dev` extra contains the same tools as the Conda environment. `viz` only adds
matplotlib (for `mpplay plan --plot` and `mpplay.viz`).

## 2. Everyday commands

| Task | Command | Make shortcut |
| --- | --- | --- |
| Start the UI (auto-opens the browser) | `mpplay serve` | `make serve` |
| Start without opening a browser | `mpplay serve --no-browser --port 8765` | |
| Run all tests | `pytest` | `make test` |
| Skip slow tests | `pytest -m "not slow"` | `make test-fast` |
| Coverage report | `pytest --cov=mpplay --cov-report=term-missing` | `make coverage` |
| Lint | `ruff check src tests examples` | `make lint` |
| Format | `ruff format src tests examples` | `make format` |
| Type check | `mypy` | `make typecheck` |
| Check the UI scripts parse | `node --check src/mpplay/web/js/**/*.js` | `make check-js` |
| Everything CI runs | | `make check` |

Install the Git hooks once so formatting and linting run on every commit:

```bash
pre-commit install
```

## 3. Working on the web UI

The UI in `src/mpplay/web/` is plain HTML, CSS and JavaScript ES modules: there is **no
build step** and no Node.js dependency. Edit a file and reload the browser. The server
sends `Cache-Control: no-cache`, so the browser always revalidates and picks up changes.

Useful tips:

- `window.mpplay` in the browser console is the application controller (state, runs,
  results), which helps with debugging.
- URL parameters set up a reproducible view, for example
  `http://127.0.0.1:8765/?scenario=maze&planners=astar,rrt_star&plan&at=0.5`
  (`plan` runs the planners on load; `at` pauses the animation at a fraction of the way).
- Colors are design tokens (CSS custom properties) in `css/app.css`. The canvas renderer
  reads them, so light and dark themes stay consistent.
- If Node.js is available, `make check-js` catches syntax errors.

## 4. Regenerating the README screenshots

`scripts/screenshots.sh` starts a temporary server and captures the images in
`docs/images/` with headless Chrome or Chromium. Set `CHROME=/path/to/chrome` if it is not
found automatically.

```bash
make screenshots
```

## 5. Release checklist

1. Update `CHANGELOG.md` and bump `__version__` in `src/mpplay/__init__.py` (and
   `version` in `CITATION.cff`).
2. `make check` must pass locally, and CI must be green.
3. Build and inspect the distributions: `python -m pip wheel . --no-deps -w dist/`, then
   check that `mpplay/web/index.html` is inside the wheel.
4. Tag the release (`git tag v0.x.y && git push --tags`) and publish to PyPI.
