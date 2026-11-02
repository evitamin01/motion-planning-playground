# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-01

First public release.

### Added

- Core library (`mpplay`): environments with circles, rotated rectangles and polygons;
  exact, vectorized collision checking for disc robots; conservative grid rasterization;
  traces; self-describing parameters; path metrics; shortcut smoothing.
- Planners: BFS, Dijkstra, A\* / Weighted A\*, Greedy Best-First, Theta\* (lazy and
  eager), RRT, RRT-Connect, RRT\*, Informed RRT\*, PRM and artificial potential fields
  (with optional random-walk escapes).
- Planner plugin interface (`@register_planner`, `--plugin`, `mpplay.planners` entry
  points) and an example plugin (EST).
- Eight curated scenarios and three random generators (maze with braiding, forest,
  shapes).
- Web UI: world editor with undo/redo, split and overlay views, synchronized step-by-step
  playback, layers (configuration space, grid discretization, potential heatmaps),
  metrics, charts with convergence curves, multi-seed benchmarks with CSV export, a
  *Learn* tab, light/dark themes, live re-planning, PNG export and URL parameters.
- Command line: `mpplay serve | planners | scenarios | plan | benchmark | export | generate`.
- Benchmark API with per-trial rows and summary statistics.
- Documentation, tests, CI, a Conda environment and contribution guidelines.

[Unreleased]: https://github.com/evitamin01/motion-planning-playground/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/evitamin01/motion-planning-playground/releases/tag/v0.1.0
