# Trace format

A trace records what a planner did so that the UI can replay it step by step. It is
produced by `mpplay.trace.Recorder` and returned in the `trace` field of a plan result:

```json
{
  "events": [["F", 3, 4], ["X", 3, 4], ["F", 4, 4], ...],
  "steps": [0, 2, 5, ...],
  "num_steps": 1234,
  "truncated": false
}
```

- `events` is a flat list. Every event is a JSON array whose first element is a one-letter
  code.
- `steps[k]` is the index of the first event of step `k`. Step `k` contains the events
  `steps[k]` up to (but excluding) `steps[k + 1]`. Events emitted before the first call to
  `Recorder.step()` belong to step 0.
- `truncated` is true if the recorder reached its event limit (1.5 million by default);
  later events were dropped, but the final path and metrics are unaffected.

Showing "the first `k` steps" means applying all events with an index below `steps[k]`, or
all events when `k == num_steps`.

## Events

| Code | Arguments | Meaning | Rendered as |
| --- | --- | --- | --- |
| `X` | `i, j` | Grid cell `(i, j)` expanded (closed) | Light cell in the run color |
| `F` | `i, j` | Grid cell added to the open set (frontier); ignored if already expanded | Darker cell |
| `S` | `x, y` | Random sample; transient, shown only while its step is the latest | Ring with crosshair |
| `N` | `x, y, layer` | Persistent vertex | Dot (`roadmap`: grey, `visited`: run color) |
| `E` | `key, x1, y1, x2, y2, layer` | Add the edge `key`, or replace it if it exists | Line (style by layer) |
| `R` | `key` | Remove the edge `key` | |
| `P` | `[[x, y], ...]` or `null` | Current best or candidate path (replaces the previous one) | Dashed line until the run finishes |
| `G` | `key, geometry` or `key, null` | Add, replace or remove an overlay shape | See below |

Edge layers: `tree` (run color), `tree2` (secondary color, for example RRT-Connect's goal
tree), `roadmap` (grey) and `trajectory` (thick run color).

Grid cell indices refer to the occupancy grid returned in the result's `grid` field:

```json
{"origin": [0.0, 0.0], "resolution": 1.0, "shape": [100, 60], "occupancy": "<base64>"}
```

Cell `(i, j)` covers `[origin_x + i * res, origin_x + (i + 1) * res]` horizontally (and the
same for `j` vertically). `occupancy` is base64-encoded `uint8` in row-major order with the
index `j * nx + i`; 1 means blocked.

## Overlay geometry

`G` events currently support ellipses:

```json
{"type": "ellipse", "center": [x, y], "rx": 40.2, "ry": 12.5, "angle": 0.52}
```

`angle` is in radians, counter-clockwise from the x axis. Informed RRT\* uses this to show
its sampling region.

## Static overlays

Besides the event stream, results may contain `overlays`, which are drawn below the
exploration:

```json
{
  "type": "heatmap", "label": "Potential",
  "origin": [0, 0], "resolution": 0.71, "shape": [140, 84],
  "values": "<base64 uint8, row-major j * nx + i, 0 = low, 255 = high>"
}
```

## Replaying in Python

`mpplay.trace.TraceState.replay(trace, upto_step=k)` reproduces the UI logic. It is used by
the matplotlib exporter and by the tests that check traces against planner statistics.
