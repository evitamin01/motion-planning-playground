"""Planning environments and problems.

An :class:`Environment` is a plain description of a 2D world (bounds, obstacles,
start, goal, robot size). It round-trips losslessly through JSON, which is the
format used by the web UI, scenario files and the HTTP API.

A :class:`Problem` wraps an environment with lazily built, cached derived data
(collision checker, rasterized occupancy grids) that planners share.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .collision import CollisionChecker
from .geometry import Point, Shape, _point, shape_from_dict

if TYPE_CHECKING:
    from .grid import OccupancyGrid

FORMAT_VERSION = 1

#: Hard limit on the size of rasterized grids, to keep the server responsive.
MAX_GRID_CELLS = 400_000


@dataclass(frozen=True)
class Environment:
    """A 2D planning environment.

    Attributes:
        bounds: Workspace bounds ``(xmin, ymin, xmax, ymax)``; the boundary acts as a wall.
        start: Start position of the robot center.
        goal: Goal position of the robot center.
        obstacles: Obstacle shapes.
        robot_radius: Radius of the disc robot (``0`` = point robot).
        resolution: Cell size used by grid-based planners.
        name: Short human-readable name.
        description: Longer description (shown in the UI).
    """

    bounds: tuple[float, float, float, float]
    start: Point
    goal: Point
    obstacles: tuple[Shape, ...] = ()
    robot_radius: float = 0.0
    resolution: float = 1.0
    name: str = "Untitled"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        xmin, ymin, xmax, ymax = (float(v) for v in self.bounds)
        if not all(math.isfinite(v) for v in (xmin, ymin, xmax, ymax)):
            raise ValueError("bounds must be finite")
        if xmax <= xmin or ymax <= ymin:
            raise ValueError("bounds must satisfy xmin < xmax and ymin < ymax")
        object.__setattr__(self, "bounds", (xmin, ymin, xmax, ymax))
        object.__setattr__(self, "start", _point(self.start))
        object.__setattr__(self, "goal", _point(self.goal))
        object.__setattr__(self, "obstacles", tuple(self.obstacles))
        if not 0 <= self.robot_radius < min(xmax - xmin, ymax - ymin) / 2:
            raise ValueError("robot_radius must be non-negative and fit inside the bounds")
        if not self.resolution > 0:
            raise ValueError("resolution must be positive")
        object.__setattr__(self, "robot_radius", float(self.robot_radius))
        object.__setattr__(self, "resolution", float(self.resolution))

    # ------------------------------------------------------------------ geometry helpers

    @property
    def width(self) -> float:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        return self.bounds[3] - self.bounds[1]

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)

    def with_changes(self, **changes: Any) -> Environment:
        """Return a copy with some fields replaced."""
        return replace(self, **changes)

    # ------------------------------------------------------------------ serialization

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": FORMAT_VERSION,
            "name": self.name,
            "description": self.description,
            "bounds": list(self.bounds),
            "start": list(self.start),
            "goal": list(self.goal),
            "robot_radius": self.robot_radius,
            "resolution": self.resolution,
            "obstacles": [o.to_dict() for o in self.obstacles],
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Environment:
        version = int(data.get("version", FORMAT_VERSION))
        if version > FORMAT_VERSION:
            raise ValueError(f"unsupported environment format version {version}")
        try:
            return cls(
                bounds=tuple(data["bounds"]),
                start=tuple(data["start"]),
                goal=tuple(data["goal"]),
                obstacles=tuple(shape_from_dict(o) for o in data.get("obstacles", [])),
                robot_radius=float(data.get("robot_radius", 0.0)),
                resolution=float(data.get("resolution", 1.0)),
                name=str(data.get("name", "Untitled")),
                description=str(data.get("description", "")),
                metadata=dict(data.get("metadata", {})),
            )
        except KeyError as exc:
            raise ValueError(f"environment is missing required field {exc.args[0]!r}") from exc

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> Environment:
        return cls.from_dict(json.loads(text))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Environment:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


class Problem:
    """A planning query: an environment plus cached derived representations.

    Planners receive a ``Problem`` instead of a bare environment so that
    expensive preprocessing (e.g. rasterization) is shared between runs.
    """

    def __init__(self, env: Environment) -> None:
        self.env = env
        self._grids: dict[float, OccupancyGrid] = {}

    @property
    def start(self) -> Point:
        return self.env.start

    @property
    def goal(self) -> Point:
        return self.env.goal

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.env.bounds

    @cached_property
    def checker(self) -> CollisionChecker:
        """Exact continuous-space collision checker."""
        return CollisionChecker(self.env.obstacles, self.env.bounds, self.env.robot_radius)

    def fork(self) -> Problem:
        """A problem with its own collision checker (and query counter) sharing cached grids."""
        clone = Problem(self.env)
        clone._grids = self._grids
        return clone

    def grid(self, resolution: float | None = None) -> OccupancyGrid:
        """Conservatively rasterized occupancy grid (cached per resolution)."""
        from .grid import OccupancyGrid

        res = float(resolution or self.env.resolution)
        if res not in self._grids:
            self._grids[res] = OccupancyGrid.from_environment(self.env, res)
        return self._grids[res]
