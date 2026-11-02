# HTTP API

`mpplay serve` exposes a small JSON API that the web UI uses. It is also convenient for
scripting from other languages. Interactive OpenAPI documentation is available at
`/docs` while the server runs.

All endpoints are under `/api`. Errors use HTTP status codes with a JSON body
`{"detail": "message"}`: 404 for unknown planners or generators and 422 for invalid input.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/info` | Version, metric metadata (label, unit, whether lower is better) and limits |
| GET | `/api/planners` | Registered planners: metadata and parameter schemas |
| GET | `/api/scenarios` | Built-in scenarios including their environments |
| GET | `/api/generators` | Environment generators with parameter schemas |
| POST | `/api/generate` | Generate an environment |
| POST | `/api/plan` | Run one planner (optionally with a trace) |
| POST | `/api/benchmark` | Repeated untraced runs with summary statistics |

## `POST /api/plan`

```json
{
  "environment": { "...": "see environment-format.md" },
  "planner": "rrt_star",
  "params": {"max_iterations": 2000},
  "seed": 1,
  "smoothing": false,
  "trace": true
}
```

The response is a plan result:

```json
{
  "planner": "rrt_star", "label": "RRT*", "params": {"max_iterations": 2000, "...": "..."},
  "seed": 1, "success": true, "message": "",
  "path": [[6.0, 8.0], "..."], "raw_path": null,
  "metrics": {"path_length": 100.9, "planning_time_ms": 512.3, "setup_time_ms": 0.0,
              "waypoints": 17, "turning_deg": 88.6, "max_turn_deg": 21.8,
              "min_clearance": 0.02, "collision_checks": 50213},
  "stats": {"iterations": 2000, "tree_size": 1650, "rewires": 1100,
            "first_solution_iteration": 242, "first_solution_cost": 115.0},
  "series": {"best_cost": [[242, 115.0], "..."]},
  "trace": {"events": ["..."], "steps": ["..."], "num_steps": 2000, "truncated": false},
  "grid": null,
  "overlays": []
}
```

A failed plan still returns status 200 with `"success": false` and an explanatory
`message`. `grid` is included for grid planners when tracing (see
[trace-format.md](trace-format.md)).

## `POST /api/benchmark`

```json
{
  "environments": [{ "...": "..." }],
  "runs": [
    {"planner": "astar"},
    {"planner": "rrt", "params": {"step_size": 2}, "label": "RRT (small steps)", "smoothing": true}
  ],
  "trials": 20,
  "seed": 0
}
```

Returns `{"rows": [...], "summary": [...]}`. Each row is one trial (scenario, run, seed,
success, metrics and `stat_*` counters). Each summary entry aggregates one
(scenario, run) pair: `success_rate` plus `<metric>_mean`, `_std`, `_median`, `_min` and
`_max` over successful trials.

## `POST /api/generate`

```json
{"generator": "maze", "params": {"cols": 12, "rows": 7, "braid": 0.2}, "seed": 42}
```

Returns an environment.

## Notes

- Planning requests are executed one at a time, so measured planning times are not
  distorted by concurrent requests.
- The server is intended for local use and binds to `127.0.0.1` by default. Do not expose
  it to untrusted networks: planning requests can be made arbitrarily expensive.
