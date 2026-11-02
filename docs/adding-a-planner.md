# Adding a planner

A planner is a Python class. Once registered, it appears in the web UI (with a parameter
form, animation, metrics and the *Learn* tab), in `mpplay planners`, in benchmarks, and in
the Python API.

## 1. The smallest planner

```python
# my_planners.py
from dataclasses import dataclass

from mpplay import Planner, PlanOutcome, register_planner
from mpplay.params import ParamsBase, param


@register_planner
class StraightLine(Planner):
    name = "straight_line"            # unique registry key
    label = "Straight line"           # display name
    family = "Baselines"              # groups planners in the UI
    summary = "Goes straight to the goal if nothing is in the way."
    description = """
Checks the straight segment between start and goal. Useful as a sanity check.
"""
    properties = {"Complete": "No", "Optimal": "Yes, when it succeeds"}
    references = []

    @dataclass
    class Params(ParamsBase):
        pass

    def plan(self, problem, rng, rec):
        rec.step()
        rec.edge("line", problem.start, problem.goal)
        if not problem.checker.segment_free(problem.start, problem.goal):
            return PlanOutcome(None, "Something is in the way.")
        return PlanOutcome([problem.start, problem.goal])
```

Load it into the UI or the CLI:

```bash
mpplay --plugin my_planners.py serve
mpplay --plugin my_planners.py plan -s open_field -p straight_line
mpplay --plugin my_planners.py benchmark -s all -p straight_line -p astar
```

A complete, realistic example is the Expansive Space Tree in
[`examples/est_planner.py`](../examples/est_planner.py).

## 2. What `plan` receives

| Argument | Type | Use it for |
| --- | --- | --- |
| `problem.start`, `problem.goal`, `problem.bounds` | tuples | The query |
| `problem.env` | `Environment` | Obstacles, robot radius, resolution, ... |
| `problem.checker` | `CollisionChecker` | Exact collision queries for the disc robot: `point_free`, `points_free`, `segment_free`, `segments_free`, `clearance` |
| `problem.grid()` | `OccupancyGrid` | The conservatively rasterized grid (cached) |
| `rng` | `numpy.random.Generator` | **All** randomness, so runs are reproducible from the seed |
| `rec` | `Recorder` | Visualization events (see below) |

Return a `PlanOutcome`:

```python
PlanOutcome(
    path=[(x0, y0), ..., (xn, yn)],   # or None on failure; must start/end at start/goal
    message="",                        # shown on failure (or as a note)
    stats={"iterations": 1234},        # any counters; shown in the metrics table
    series={"best_cost": [[it, cost], ...]},  # optional time series (convergence chart)
    overlays=[...],                    # optional static layers, e.g. heatmaps
)
```

You don't need to compute metrics, time the run or validate the path: `run_planner` does
that, and rejects paths that collide.

Raise `mpplay.PlanningError("message")` to abort with a user-facing message (for example
when the start is in an occupied grid cell).

## 3. Parameters

Declare parameters as dataclass fields with `param(default, ...)`:

```python
@dataclass
class Params(ParamsBase):
    max_iterations: int = param(5000, min=10, max=100_000, step=100,
                                label="Max iterations", help="Sampling budget.")
    step_size: float = param(2.0, min=0.05, max=50.0, step=0.05, label="Step size")
    heuristic: str = param("euclidean", choices=["euclidean", "manhattan"])
    bidirectional: bool = param(False, help="Grow a second tree from the goal.")
    exotic_knob: float = param(0.3, min=0, max=1, advanced=True)  # under "Advanced"
```

Supported types are `int`, `float`, `bool` and `str` (with `choices`). Values arrive
validated and converted in `self.params`. In the UI, numeric fields with `min` and `max`
get a slider (logarithmic when the range spans more than two orders of magnitude).

## 4. Recording a trace

Call `rec.step()` at the start of every iteration you want to be one animation frame, then
emit events:

| Method | Draws |
| --- | --- |
| `rec.expand(i, j)` / `rec.frontier(i, j)` | Grid cells closed / added to the open set |
| `rec.sample(p)` | A random sample, visible only during its step |
| `rec.node(p, layer)` | A persistent vertex (`"roadmap"` = grey, `"visited"` = run color) |
| `rec.edge(key, a, b, layer)` | An edge; reusing a `key` replaces the edge (rewiring) |
| `rec.remove_edge(key)` | Removes an edge |
| `rec.path(points)` | The current best or candidate path (dashed until the run finishes) |
| `rec.overlay(key, geometry)` | Overlay shapes such as `{"type": "ellipse", ...}` |

Edge layers: `"tree"` (run color), `"tree2"` (secondary color, for example a goal tree),
`"roadmap"` (grey), `"trajectory"` (thick). Skip expensive work for visualization when
`rec.enabled` is false (benchmarks use a recorder that discards everything). See
[trace-format.md](trace-format.md) for the wire format.

## 5. Grid planners

Subclass `GridPlanner` to get rasterization during `setup` and helpers:

```python
from mpplay import GridPlanner

@register_planner
class MyGridSearch(GridPlanner):
    ...
    def plan(self, problem, rng, rec):
        grid = problem.grid()
        start, goal = self.endpoints(problem, grid)     # cells; raises PlanningError if blocked
        ...                                             # search over grid.occupied[i, j]
        return PlanOutcome(self.cells_to_path(problem, grid, cells))
```

`grid.blocked_bytes()` returns a flat `bytes` occupancy (`index = i * ny + j`) for fast
pure-Python loops, `grid.line_of_sight(a, b)` does exact grid traversal, and
`grid.center(i, j)` converts cells to world coordinates. For 8-connected moves, follow the
"no corner cutting" rule (both adjacent straight cells must be free) to keep paths valid.

## 6. Distributing planners as a package

Add an entry point to your package's `pyproject.toml`; `mpplay` imports it automatically:

```toml
[project.entry-points."mpplay.planners"]
my_planners = "my_package.planners"
```

## 7. Testing

The built-in planners are tested against every scenario in `tests/test_planners.py`, and
the same pattern works for plugins:

```python
from mpplay import get_scenario, run_planner

def test_my_planner_solves_bug_trap():
    result = run_planner(get_scenario("bug_trap"), "my_planner", seed=0, raise_errors=True)
    assert result.success, result.message
```

If you contribute a planner to this repository, add it to
`src/mpplay/planners/`, import its module in `planners/__init__.py`, give it a clear
`description` with references, and add tests.
