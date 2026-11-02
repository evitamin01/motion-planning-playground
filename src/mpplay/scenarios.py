"""Built-in scenarios and procedural environment generators.

Scenarios are curated environments that each highlight a characteristic
challenge (local minima, narrow passages, clutter, ...). Generators create
random environments from a seed and a few parameters; they are exposed in
the UI under "Generate".
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from .environment import Environment
from .geometry import Circle, Point, Polygon, Rectangle, Shape
from .params import ParamsBase, param

W, H = 100.0, 60.0
BOUNDS = (0.0, 0.0, W, H)


def _wall(x0: float, y0: float, x1: float, y1: float) -> Rectangle:
    return Rectangle.from_bounds(x0, y0, x1, y1)


# --------------------------------------------------------------------------- generators


@dataclass
class ForestParams(ParamsBase):
    count: int = param(60, min=1, max=500, step=1, label="Trees", help="Number of circles.")
    min_radius: float = param(1.5, min=0.2, max=20.0, step=0.1, label="Min radius")
    max_radius: float = param(4.0, min=0.2, max=20.0, step=0.1, label="Max radius")
    width: float = param(W, min=10.0, max=500.0, step=1.0, label="Width", advanced=True)
    height: float = param(H, min=10.0, max=500.0, step=1.0, label="Height", advanced=True)


@dataclass
class MazeParams(ParamsBase):
    cols: int = param(10, min=2, max=60, step=1, label="Columns")
    rows: int = param(6, min=2, max=40, step=1, label="Rows")
    wall_thickness: float = param(1.5, min=0.1, max=10.0, step=0.1, label="Wall thickness")
    braid: float = param(
        0.0,
        min=0.0,
        max=1.0,
        step=0.05,
        label="Loops",
        help="Fraction of dead ends opened up, creating alternative routes.",
    )
    width: float = param(W, min=10.0, max=500.0, step=1.0, label="Width", advanced=True)
    height: float = param(H, min=10.0, max=500.0, step=1.0, label="Height", advanced=True)


@dataclass
class ShapesParams(ParamsBase):
    count: int = param(25, min=1, max=300, step=1, label="Obstacles")
    min_size: float = param(3.0, min=0.5, max=50.0, step=0.5, label="Min size")
    max_size: float = param(12.0, min=0.5, max=50.0, step=0.5, label="Max size")
    width: float = param(W, min=10.0, max=500.0, step=1.0, label="Width", advanced=True)
    height: float = param(H, min=10.0, max=500.0, step=1.0, label="Height", advanced=True)


def _endpoints(width: float, height: float) -> tuple[Point, Point]:
    margin = min(width, height) * 0.08
    return (margin, height / 2), (width - margin, height / 2)


def generate_forest(p: ForestParams, seed: int = 0) -> Environment:
    rng = np.random.default_rng(seed)
    start, goal = _endpoints(p.width, p.height)
    lo, hi = sorted((p.min_radius, p.max_radius))
    keep_clear = hi + 2.0
    obstacles: list[Shape] = []
    attempts = 0
    while len(obstacles) < p.count and attempts < 100 * p.count:
        attempts += 1
        r = float(rng.uniform(lo, hi))
        c = rng.uniform([0, 0], [p.width, p.height])
        if min(math.dist(c, start), math.dist(c, goal)) < r + keep_clear:
            continue
        obstacles.append(Circle((float(c[0]), float(c[1])), r))
    return Environment(
        bounds=(0.0, 0.0, p.width, p.height),
        start=start,
        goal=goal,
        obstacles=tuple(obstacles),
        name="Random forest",
        description=f"{len(obstacles)} randomly placed circular obstacles (seed {seed}).",
    )


def generate_maze(p: MazeParams, seed: int = 0) -> Environment:
    """A perfect maze (recursive backtracker), optionally braided to create loops."""
    rng = np.random.default_rng(seed)
    cols, rows = p.cols, p.rows
    cw, ch = p.width / cols, p.height / rows
    t = min(p.wall_thickness, 0.8 * min(cw, ch))
    # Interior walls: hwall[c][r] separates (c, r-1)|(c, r) for r in 1..rows-1;
    # vwall[c][r] separates (c-1, r)|(c, r) for c in 1..cols-1.
    hwall = [[True] * (rows + 1) for _ in range(cols)]
    vwall = [[True] * rows for _ in range(cols + 1)]

    def remove_between(a: tuple[int, int], b: tuple[int, int]) -> None:
        (c0, r0), (c1, r1) = a, b
        if c0 == c1:
            hwall[c0][max(r0, r1)] = False
        else:
            vwall[max(c0, c1)][r0] = False

    def neighbors(c: int, r: int) -> list[tuple[int, int]]:
        cand = [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        return [(x, y) for x, y in cand if 0 <= x < cols and 0 <= y < rows]

    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        cell = stack[-1]
        options = [n for n in neighbors(*cell) if n not in visited]
        if not options:
            stack.pop()
            continue
        nxt = options[int(rng.integers(len(options)))]
        remove_between(cell, nxt)
        visited.add(nxt)
        stack.append(nxt)

    if p.braid > 0:
        for c in range(cols):
            for r in range(rows):
                walls = [
                    (n, hwall[c][max(r, n[1])] if n[0] == c else vwall[max(c, n[0])][r])
                    for n in neighbors(c, r)
                ]
                closed = [n for n, present in walls if present]
                is_dead_end = len(closed) == len(walls) - 1
                if is_dead_end and closed and rng.random() < p.braid:
                    remove_between((c, r), closed[int(rng.integers(len(closed)))])

    obstacles: list[Shape] = []
    # Merge runs of collinear wall segments into single rectangles.
    for r in range(1, rows):
        c = 0
        while c < cols:
            if not hwall[c][r]:
                c += 1
                continue
            c_end = c
            while c_end + 1 < cols and hwall[c_end + 1][r]:
                c_end += 1
            obstacles.append(
                _wall(c * cw - t / 2, r * ch - t / 2, (c_end + 1) * cw + t / 2, r * ch + t / 2)
            )
            c = c_end + 1
    for c in range(1, cols):
        r = 0
        while r < rows:
            if not vwall[c][r]:
                r += 1
                continue
            r_end = r
            while r_end + 1 < rows and vwall[c][r_end + 1]:
                r_end += 1
            obstacles.append(
                _wall(c * cw - t / 2, r * ch - t / 2, c * cw + t / 2, (r_end + 1) * ch + t / 2)
            )
            r = r_end + 1
    return Environment(
        bounds=(0.0, 0.0, p.width, p.height),
        start=(cw / 2, ch / 2),
        goal=(p.width - cw / 2, p.height - ch / 2),
        obstacles=tuple(obstacles),
        resolution=round(min(cw, ch) / 10, 3) if min(cw, ch) < 10 else 1.0,
        name="Random maze",
        description=f"A {cols}x{rows} maze (seed {seed}).",
    )


def generate_shapes(p: ShapesParams, seed: int = 0) -> Environment:
    rng = np.random.default_rng(seed)
    start, goal = _endpoints(p.width, p.height)
    lo, hi = sorted((p.min_size, p.max_size))
    obstacles: list[Shape] = []
    attempts = 0
    while len(obstacles) < p.count and attempts < 100 * p.count:
        attempts += 1
        size = float(rng.uniform(lo, hi))
        c = rng.uniform([0, 0], [p.width, p.height])
        if min(math.dist(c, start), math.dist(c, goal)) < size * 0.75 + 3.0:
            continue
        center = (float(c[0]), float(c[1]))
        kind = rng.integers(3)
        shape: Shape
        if kind == 0:
            shape = Circle(center, size / 2)
        elif kind == 1:
            aspect = float(rng.uniform(0.3, 1.0))
            shape = Rectangle(center, (size, size * aspect), float(rng.uniform(0, 180)))
        else:
            n = int(rng.integers(3, 7))
            angles = np.sort(rng.uniform(0, 2 * math.pi, n))
            radii = rng.uniform(0.5, 1.0, n) * size / 2
            pts = tuple(
                (center[0] + float(rr * math.cos(a)), center[1] + float(rr * math.sin(a)))
                for a, rr in zip(angles, radii, strict=True)
            )
            try:
                shape = Polygon(pts)
            except ValueError:
                continue
        obstacles.append(shape)
    return Environment(
        bounds=(0.0, 0.0, p.width, p.height),
        start=start,
        goal=goal,
        obstacles=tuple(obstacles),
        name="Random shapes",
        description=f"{len(obstacles)} random circles, rectangles and polygons (seed {seed}).",
    )


@dataclass(frozen=True)
class Generator:
    name: str
    label: str
    description: str
    Params: type[ParamsBase]
    fn: Callable[[Any, int], Environment]

    def generate(self, params: dict[str, Any] | None = None, seed: int = 0) -> Environment:
        return self.fn(self.Params.from_dict(params), seed)

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "params": self.Params.schema(),
        }


GENERATORS: dict[str, Generator] = {
    g.name: g
    for g in [
        Generator(
            "maze", "Maze", "Perfect or braided maze on a regular grid.", MazeParams, generate_maze
        ),
        Generator(
            "forest",
            "Forest",
            "Randomly scattered circular obstacles.",
            ForestParams,
            generate_forest,
        ),
        Generator(
            "shapes",
            "Random shapes",
            "A mix of random circles, rotated rectangles and polygons.",
            ShapesParams,
            generate_shapes,
        ),
    ]
}


# --------------------------------------------------------------------------- curated scenarios


def _open_field() -> Environment:
    return Environment(
        bounds=BOUNDS,
        start=(8, 30),
        goal=(92, 30),
        name="Open field",
        description="No obstacles at all: a baseline that shows how each planner explores "
        "space and how far its path is from the straight line.",
    )


def _scattered() -> Environment:
    obstacles: tuple[Shape, ...] = (
        Rectangle((28, 22), (8, 22)),
        Rectangle((28, 51), (8, 10)),
        Circle((50, 32), 8),
        Rectangle((72, 16), (16, 6), 30),
        Polygon(((62, 40), (80, 50), (64, 56))),
        Circle((86, 34), 5),
        Rectangle((14, 44), (10, 5), -20),
        Polygon(((40, 4), (52, 6), (54, 14), (44, 17), (38, 11))),
    )
    return Environment(
        bounds=BOUNDS,
        start=(6, 8),
        goal=(94, 52),
        obstacles=obstacles,
        name="Scattered obstacles",
        description="A handful of mixed obstacles (rectangles, circles, polygons) with several "
        "homotopically distinct routes.",
    )


def _slalom() -> Environment:
    obstacles = (
        Circle((28, 24), 7),
        Circle((50, 38), 7),
        Circle((72, 24), 7),
        Rectangle((50, 8), (10, 6), 15),
    )
    return Environment(
        bounds=BOUNDS,
        start=(6, 30),
        goal=(94, 30),
        obstacles=obstacles,
        name="Slalom",
        description="A few well-separated round obstacles. Even purely reactive methods such "
        "as potential fields succeed here, unlike in the trap and maze scenarios.",
    )


def _bug_trap() -> Environment:
    obstacles = (
        _wall(28, 40, 57, 42),  # top
        _wall(28, 18, 57, 20),  # bottom
        _wall(55, 18, 57, 42),  # closed side, facing the goal
    )
    return Environment(
        bounds=BOUNDS,
        start=(45, 30),
        goal=(90, 30),
        obstacles=obstacles,
        name="Bug trap",
        description="The start sits inside a U-shaped obstacle whose closed side faces the "
        "goal. Greedy search wastes effort in the dead end and potential fields get "
        "stuck in a local minimum.",
    )


def _narrow_passage() -> Environment:
    gap = 3.0
    obstacles = (
        _wall(33, 0, 37, 48 - gap / 2),
        _wall(33, 48 + gap / 2, 37, H),
        _wall(63, 0, 67, 12 - gap / 2),
        _wall(63, 12 + gap / 2, 67, H),
    )
    return Environment(
        bounds=BOUNDS,
        start=(10, 10),
        goal=(90, 50),
        obstacles=obstacles,
        name="Narrow passages",
        description="Two thick walls, each with a single narrow gap. Few random samples land "
        "inside the gaps, which makes this hard for sampling-based planners.",
    )


def _maze() -> Environment:
    env = generate_maze(MazeParams(), seed=7)
    return env.with_changes(
        name="Maze",
        description="A 10x6 perfect maze: there is exactly one route, so all complete planners "
        "find the same corridor but explore very differently.",
    )


def _forest() -> Environment:
    env = generate_forest(ForestParams(count=70), seed=3)
    return env.with_changes(
        name="Forest",
        description="Dense clutter of circular obstacles with many narrow gaps and many "
        "nearly equivalent routes.",
    )


def _office() -> Environment:
    t = 1.0
    walls = [
        # horizontal wall at y = 30 with three doors
        _wall(0, 30 - t / 2, 12, 30 + t / 2),
        _wall(18, 30 - t / 2, 45, 30 + t / 2),
        _wall(51, 30 - t / 2, 78, 30 + t / 2),
        _wall(84, 30 - t / 2, 100, 30 + t / 2),
        # vertical wall at x = 33 with a door in the upper half
        _wall(33 - t / 2, 0, 33 + t / 2, 42),
        _wall(33 - t / 2, 48, 33 + t / 2, 60),
        # vertical wall at x = 66 with a door in the lower half
        _wall(66 - t / 2, 0, 66 + t / 2, 10),
        _wall(66 - t / 2, 16, 66 + t / 2, 60),
    ]
    furniture: list[Shape] = [
        Rectangle((20, 14), (10, 5)),
        Circle((8, 48), 3),
        Rectangle((22, 50), (6, 10)),
        Rectangle((50, 46), (12, 6)),
        Circle((48, 14), 4),
        Rectangle((82, 18), (8, 8), 45),
        Rectangle((80, 48), (14, 4)),
        Circle((94, 40), 2.5),
    ]
    return Environment(
        bounds=BOUNDS,
        start=(6, 6),
        goal=(94, 54),
        obstacles=tuple(walls + furniture),
        robot_radius=1.0,
        name="Office",
        description="Six rooms connected by doors along a single winding route, with furniture. "
        "The robot is a disc of radius 1, so obstacles are inflated in configuration space.",
    )


@dataclass(frozen=True)
class Scenario:
    name: str
    factory: Callable[[], Environment]

    def build(self) -> Environment:
        return self.factory()

    def info(self) -> dict[str, Any]:
        env = self.build()
        return {
            "name": self.name,
            "label": env.name,
            "description": env.description,
            "environment": env.to_dict(),
        }


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in [
        Scenario("scattered", _scattered),
        Scenario("slalom", _slalom),
        Scenario("bug_trap", _bug_trap),
        Scenario("narrow_passage", _narrow_passage),
        Scenario("maze", _maze),
        Scenario("forest", _forest),
        Scenario("office", _office),
        Scenario("open_field", _open_field),
    ]
}


def get_scenario(name: str) -> Environment:
    try:
        return SCENARIOS[name].build()
    except KeyError:
        known = ", ".join(SCENARIOS)
        raise KeyError(f"unknown scenario {name!r}; available: {known}") from None
