# Contributing

Thank you for helping to improve Motion Planning Playground! Contributions of all sizes
are welcome: bug reports, scenarios, planners, UI improvements, documentation and
teaching material.

## Ways to contribute

- **Report a bug or suggest a feature** using the
  [issue templates](https://github.com/evitamin01/motion-planning-playground/issues/new/choose).
  For bugs, include the environment JSON (*Save environment* in the UI) and the planner
  settings if possible.
- **Add a planner.** Follow [docs/adding-a-planner.md](docs/adding-a-planner.md). Good
  candidates are listed in the README roadmap; please open an issue first for larger
  additions.
- **Add a scenario** that highlights an interesting property of some algorithms (in
  `src/mpplay/scenarios.py`, with a description of what it demonstrates).
- **Improve the UI or the docs.** Small, focused pull requests are easiest to review.

## Development workflow

1. Fork the repository and create a branch: `git checkout -b feature/my-change`.
2. Set up the environment as described in [docs/development.md](docs/development.md):

   ```bash
   conda env create --prefix ./.conda --file environment.yml
   conda activate ./.conda
   pre-commit install
   ```

3. Make your change, including tests (see below), and run the checks:

   ```bash
   make check        # ruff, mypy and pytest
   make check-js     # if you touched the web UI and have Node.js
   ```

4. Update the documentation and `CHANGELOG.md` (under *Unreleased*) where relevant.
5. Open a pull request that describes what you changed and why. Screenshots or GIFs help
   for UI changes.

## Guidelines

- **Python:** 3.10+, type hints throughout (mypy must pass), formatted and linted with
  ruff (line length 100). Keep the core (`mpplay` without `server`) free of web
  dependencies.
- **Planners:** take all randomness from the provided `rng`, report progress through the
  recorder, and give every planner a clear `summary`, `description`, `properties` and
  `references`. Correctness matters more than speed, but keep the defaults responsive
  (well under a second on the built-in scenarios when possible).
- **Tests:** new planners should solve the built-in scenarios (see
  `tests/test_planners.py`); bug fixes should come with a regression test. Keep tests
  fast, and mark tests that take more than a few seconds with `@pytest.mark.slow`.
- **Web UI:** plain ES modules without a build step or third-party runtime dependencies.
  Use the CSS design tokens for colors so both themes keep working, and check that the
  layout holds up in narrow windows.
- **Commits:** write descriptive messages in the imperative mood ("Add Lazy PRM"), and
  keep unrelated changes in separate commits.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you
agree to uphold it.
