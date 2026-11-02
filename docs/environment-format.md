# Environment format

Environments are stored as JSON. The same format is used by the web UI (open/save), the
CLI (`mpplay export`, `mpplay plan --env`), the HTTP API and `Environment.save/load` in
Python.

```json
{
  "version": 1,
  "name": "My world",
  "description": "Optional text shown in the UI.",
  "bounds": [0, 0, 100, 60],
  "start": [5, 5],
  "goal": [95, 55],
  "robot_radius": 0.5,
  "resolution": 1.0,
  "obstacles": [
    {"type": "rect", "center": [30, 20], "size": [8, 20], "angle": 15},
    {"type": "circle", "center": [60, 40], "radius": 6},
    {"type": "polygon", "points": [[70, 5], [85, 8], [78, 18]]}
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `version` | no (default 1) | Format version; files from newer versions are rejected |
| `bounds` | yes | `[xmin, ymin, xmax, ymax]` in world units; the border is a wall |
| `start`, `goal` | yes | Positions of the robot center |
| `obstacles` | no | List of shapes (see below) |
| `robot_radius` | no (default 0) | Radius of the disc robot; 0 is a point robot |
| `resolution` | no (default 1) | Cell size of the occupancy grid used by grid planners |
| `name`, `description` | no | Shown in the UI and in benchmark tables |
| `metadata` | no | Free-form object, preserved but not interpreted |

The y axis points up. Units are arbitrary but shared by all fields; the built-in scenarios
use a 100 × 60 world.

## Shapes

| Type | Fields | Notes |
| --- | --- | --- |
| `rect` | `center`, `size` (`[width, height]`), `angle` (degrees, counter-clockwise, default 0) | Rotated about its center |
| `circle` | `center`, `radius` | |
| `polygon` | `points` (at least 3 `[x, y]` vertices) | Simple polygons, convex or concave. Self-intersecting outlines follow the even-odd rule |

Obstacles may overlap. A path is collision-free if the robot disc, swept along it, never
touches an obstacle or the border.

## Grid resolution

Grid planners rasterize the world conservatively: a cell counts as blocked if any part of
it, grown by the robot radius, touches an obstacle. Coarse resolutions can therefore close
narrow gaps, or block a start or goal that lies close to an obstacle; the planner then
reports this. Grids are limited to 400,000 cells.
