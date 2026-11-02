from __future__ import annotations

import base64

import numpy as np
import pytest

from mpplay.environment import Environment, Problem
from mpplay.geometry import Circle, Polygon, Rectangle
from mpplay.grid import OccupancyGrid


def make_env(radius: float = 0.0, resolution: float = 1.0) -> Environment:
    return Environment(
        bounds=(0, 0, 30, 20),
        start=(1.5, 1.5),
        goal=(28.5, 18.5),
        obstacles=(
            Rectangle((8, 10), (2, 12), angle=20),
            Circle((18, 6), 3.2),
            Polygon(((20, 14), (27, 12), (25, 18), (22, 16))),
        ),
        robot_radius=radius,
        resolution=resolution,
    )


def test_shape_and_coordinates():
    grid = OccupancyGrid.from_environment(make_env(resolution=0.5))
    assert grid.shape == (60, 40)
    assert grid.cell_of((0.1, 0.1)) == (0, 0)
    assert grid.cell_of((29.9, 19.9)) == (59, 39)
    assert grid.cell_of((-1, 5)) is None
    assert grid.center(0, 0) == (0.25, 0.25)
    assert grid.cell_of(grid.center(17, 23)) == (17, 23)


@pytest.mark.parametrize(("radius", "resolution"), [(0.0, 1.0), (0.0, 0.7), (0.8, 0.5), (0.5, 0.7)])
def test_rasterization_is_conservative(radius, resolution):
    """Every point of a free cell (closed box) is clear of obstacles.

    Together with the center-based wall rule this guarantees that polylines through
    the centers of adjacent free cells are collision-free in continuous space.
    Points outside the bounds or within the robot radius of a wall are excluded:
    walls are handled by the (convex) center rule instead.
    """
    env = make_env(radius, resolution)
    grid = OccupancyGrid.from_environment(env)
    checker = Problem(env).checker
    rng = np.random.default_rng(0)
    free = np.argwhere(~grid.occupied)
    assert len(free) > 0.3 * grid.occupied.size
    centers = np.array([grid.center(i, j) for i, j in free])
    assert checker.points_free(centers).all()
    offsets = rng.uniform(-0.5, 0.5, size=(len(free), 4, 2)) * resolution
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * resolution / 2
    pts = np.concatenate([(centers[:, None, :] + offsets), centers[:, None, :] + corners], axis=1)
    pts = pts.reshape(-1, 2)
    pts = pts[~_near_wall(pts, env, radius)]
    assert checker.points_free(pts).all()


def _near_wall(pts, env, radius):
    xmin, ymin, xmax, ymax = env.bounds
    return (
        (pts[..., 0] < xmin + radius)
        | (pts[..., 0] > xmax - radius)
        | (pts[..., 1] < ymin + radius)
        | (pts[..., 1] > ymax - radius)
    )


def test_paths_through_free_cells_are_valid():
    """Random walks over 8-connected free cells (no corner cutting) never collide."""
    env = make_env(0.6, 0.7)
    grid = OccupancyGrid.from_environment(env)
    checker = Problem(env).checker
    rng = np.random.default_rng(5)
    free = [tuple(c) for c in np.argwhere(~grid.occupied)]
    moves = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    for start in rng.choice(len(free), size=40, replace=False):
        i, j = free[start]
        pts = [grid.center(i, j)]
        for _ in range(60):
            di, dj = moves[rng.integers(len(moves))]
            ni, nj = i + di, j + dj
            ok = grid.is_free((ni, nj)) and not (
                di and dj and not (grid.is_free((ni, j)) and grid.is_free((i, nj)))
            )
            if ok:
                i, j = ni, nj
                pts.append(grid.center(i, j))
        p = np.asarray(pts)
        assert checker.segments_free(p[:-1], p[1:]).all()


def test_obstacle_cells_are_occupied():
    env = make_env()
    grid = OccupancyGrid.from_environment(env)
    checker = Problem(env).checker
    centers = np.array([grid.center(i, j) for i in range(grid.nx) for j in range(grid.ny)])
    blocked_centers = ~checker.points_free(centers)
    assert grid.occupied.ravel()[blocked_centers].all()


def test_line_of_sight():
    env = Environment(
        bounds=(0, 0, 10, 10),
        start=(0.5, 0.5),
        goal=(9.5, 9.5),
        obstacles=(Rectangle.from_bounds(4.2, 4.2, 5.8, 5.8),),
    )
    grid = OccupancyGrid.from_environment(env)
    assert grid.line_of_sight((0, 9), (9, 9))  # along the top row
    assert not grid.line_of_sight((0, 0), (9, 9))  # through the block
    assert grid.line_of_sight((0, 0), (0, 0))
    assert grid.line_of_sight((0, 1), (9, 3))


def test_line_of_sight_corner_rule():
    """A segment passing exactly through a cell corner needs both side cells free."""
    env = Environment(
        bounds=(0, 0, 10, 10),
        start=(0.5, 0.5),
        goal=(9.5, 9.5),
        obstacles=(
            Rectangle.from_bounds(4.2, 5.2, 4.8, 5.8),  # blocks cell (4, 5)
            Rectangle.from_bounds(5.2, 4.2, 5.8, 4.8),  # blocks cell (5, 4)
        ),
    )
    grid = OccupancyGrid.from_environment(env)
    assert grid.occupied[4, 5] and grid.occupied[5, 4]
    assert not grid.occupied[4, 4] and not grid.occupied[5, 5]
    assert not grid.line_of_sight((3, 3), (6, 6))
    assert grid.line_of_sight((3, 6), (6, 9))


def test_to_dict_roundtrip():
    grid = OccupancyGrid.from_environment(make_env())
    data = grid.to_dict()
    nx, ny = data["shape"]
    raw = np.frombuffer(base64.b64decode(data["occupancy"]), dtype=np.uint8).reshape(ny, nx)
    np.testing.assert_array_equal(raw.T.astype(bool), grid.occupied)


def test_grid_size_limit():
    env = make_env(resolution=0.01)
    with pytest.raises(ValueError, match="exceeds the limit"):
        OccupancyGrid.from_environment(env)


def test_problem_caches_grids():
    problem = Problem(make_env())
    assert problem.grid() is problem.grid()
    assert problem.grid(0.5) is not problem.grid()
    assert problem.fork().grid() is problem.grid()
