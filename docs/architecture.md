# Architecture

Motion Planning Playground has three layers with clear responsibilities:

```
┌────────────────────────────── browser ───────────────────────────────┐
│ web/  (vanilla ES modules, Canvas 2D)                                │
│  app.js      state, undo/redo, persistence, planning orchestration   │
│  editor.js   tools and pointer interaction  views.js  canvas panels  │
│  renderer.js draws worlds + traces          trace.js  trace replay   │
│  playback.js synchronized animation         ui/*      panels, charts │
└───────────────▲────────────────────────────────────────┬─────────────┘
                │ JSON over HTTP (same origin)           │
┌───────────────┴────────────── server/ ─────────────────▼─────────────┐
│ FastAPI app: /api/planners, /api/scenarios, /api/plan, ...           │
│ LRU cache of Problems (shares rasterized grids between requests)     │
│ planning lock (one planner at a time, so timings stay comparable)    │
└───────────────▲──────────────────────────────────────────────────────┘
                │ Python calls
┌───────────────┴────────────── core (mpplay) ─────────────────────────┐
│ environment.py  Environment (JSON-serializable) + Problem (caches)   │
│ geometry.py / collision.py   shapes, exact vectorized checks         │
│ grid.py         conservative rasterization, line of sight            │
│ planners/       registry, Planner base class, built-in planners      │
│ runner.py       run_planner: timing, validation, smoothing, metrics  │
│ trace.py        Recorder (events + steps), TraceState (replay)       │
│ params.py       self-describing parameter dataclasses                │
│ benchmark.py    repeated untraced runs + statistics                  │
│ scenarios.py    curated scenarios and generators                     │
│ cli.py / viz.py command line and matplotlib output                   │
└──────────────────────────────────────────────────────────────────────┘
```

The core has no dependency on the server or the UI. Everything the UI can do is available
from Python and the CLI, and new planners automatically work in all three.

## World model

An `Environment` holds the workspace bounds, obstacles (circles, possibly rotated
rectangles, and simple polygons), the start and goal, the robot radius and the grid
resolution. It is immutable and round-trips through JSON (see
[environment-format.md](environment-format.md)).

A `Problem` wraps an environment and lazily caches derived data:

- `problem.checker` is an exact `CollisionChecker` for a disc robot. Point, segment and
  clearance queries are vectorized with NumPy and use an axis-aligned bounding-box broad
  phase, so maps with thousands of edges stay fast.
- `problem.grid(resolution)` is an `OccupancyGrid`, rasterized **conservatively**: a cell is
  blocked if any part of the square cell, grown by the robot radius, touches an obstacle.
  A polyline through the centers of free, adjacent cells (without corner cutting) is
  therefore collision-free in continuous space. This is what allows grid-based and
  sampling-based planners to be compared on equal terms.

## Planners

A planner is a subclass of `Planner` registered with `@register_planner`. It declares:

- metadata (`name`, `label`, `family`, `summary`, `description`, `properties`,
  `references`), which drives the UI and the *Learn* tab;
- a `Params` dataclass whose fields use `param(...)`. The schema is served to the UI, which
  renders forms from it, and values are validated and coerced in one place;
- `setup(problem)` for untimed preprocessing (grid planners rasterize here);
- `plan(problem, rng, rec)`, which returns a `PlanOutcome` (path, message, stats,
  time series, overlays).

`run_planner` (in `runner.py`) wraps every run in the same way:

1. checks that the start and goal are collision-free;
2. runs `setup` and `plan` on a forked problem with its own collision-check counter, timing
   `plan` only;
3. **validates** the returned path (it must start and end at the right points and every
   segment must be collision-free), which protects against buggy plugins;
4. optionally applies greedy shortcut smoothing;
5. computes metrics (length, waypoints, turning, sharpest turn, clearance, checks).

## Traces

While planning, a planner reports what it does to a `Recorder`: grid cells expanded or
added to the frontier, samples, nodes, edges (keyed, so RRT\* can rewire them), candidate
paths and overlay geometry. Events are grouped into *steps*, typically one iteration or
expansion each. The format is documented in [trace-format.md](trace-format.md).

Recording is optional: benchmarks use a `NullRecorder`, so they pay no visualization
overhead.

## Server

`server/app.py` exposes the core through a small JSON API (see [http-api.md](http-api.md))
and serves the static UI. Requests that plan are serialized with a lock: planners are
CPU-bound Python code, and running several in threads only makes them compete for the
GIL, which would distort the measured planning times. The server binds to `127.0.0.1` by
default and is meant for local use.

## Web UI

The UI is deliberately framework-free (ES modules, Canvas 2D, inline SVG icons and charts),
so it works offline and contributors need no JavaScript toolchain.

- `App` (in `app.js`) owns the state: environment, runs, results, view options and
  undo/redo history. It persists the workspace in `localStorage` and coordinates the
  modules through a tiny event bus (`env`, `runs`, `results`, `selection`, `tool`).
- `Views` lays out one canvas per planner run (*Split*) or a single canvas (*Overlay*) and
  chooses the grid that maximizes the map size.
- `TraceState` (in `trace.js`) incrementally applies trace events up to a step; seeking
  backwards replays from the start. Grid exploration is drawn through an offscreen
  `ImageData` canvas, so large grids stay cheap.
- `Player` advances a shared clock. Runs are synchronized either *by step* (all runs
  advance the same number of steps per frame, so you can see which finishes first) or *by
  progress* (all runs finish together).
- The renderer reads its colors from CSS custom properties, so the canvas follows the
  light and dark themes.

## Design decisions

| Decision | Rationale |
| --- | --- |
| Python core, browser UI | Python is the lingua franca of robotics research and teaching; the browser gives a rich, portable UI without installing a GUI toolkit. |
| Exact geometry instead of discretized collision checks | Results are trustworthy: no reported path ever clips an obstacle corner. |
| Conservative rasterization | Grid paths are valid in continuous space, so path metrics compare fairly across planner families. |
| Traces computed on the server, animated on the client | Planning runs at full speed; playback (scrubbing, speed, sync) is instant and needs no further requests. |
| Dataclass parameters with metadata | One declaration gives validation, CLI parsing, documentation and UI forms. |
| No frontend build step | Lowers the barrier for contributors and keeps the package self-contained. |
