from __future__ import annotations

import numpy as np
import pytest

from mpplay.collision import CollisionChecker
from mpplay.geometry import Circle, Polygon, Rectangle

BOUNDS = (0.0, 0.0, 20.0, 10.0)
U_SHAPE = Polygon(((4, 2), (8, 2), (8, 8), (4, 8), (4, 7), (7, 7), (7, 3), (4, 3)))


@pytest.fixture
def checker() -> CollisionChecker:
    return CollisionChecker(
        [Rectangle((5, 5), (2, 2)), Circle((10, 5), 1), Polygon(((12, 0), (14, 0), (13, 3)))],
        BOUNDS,
    )


def test_points(checker):
    assert not checker.point_free((5, 5))  # inside rectangle
    assert not checker.point_free((10, 5.5))  # inside circle
    assert not checker.point_free((13, 1))  # inside triangle
    assert checker.point_free((1, 1))
    assert not checker.point_free((-1, 5))  # outside the bounds
    assert not checker.point_free((21, 5))


def test_points_vectorized_matches_scalar(checker):
    rng = np.random.default_rng(0)
    pts = rng.uniform([-1, -1], [21, 11], size=(500, 2))
    batch = checker.points_free(pts)
    assert batch.tolist() == [checker.point_free(p) for p in pts]


def test_segments(checker):
    assert not checker.segment_free((0.5, 5), (9, 5))  # through the rectangle
    assert not checker.segment_free((0.5, 0.5), (19, 0.5))  # through the triangle
    assert checker.segment_free((0.5, 9), (19, 9))
    assert checker.segment_free((1, 1), (1, 1))  # degenerate segment in free space


def test_segment_inside_polygon_is_not_free():
    big = CollisionChecker([Rectangle((10, 5), (10, 8))], BOUNDS)
    assert not big.segment_free((8, 5), (12, 5))


def test_concave_polygon():
    c = CollisionChecker([U_SHAPE], BOUNDS)
    assert c.point_free((5, 5))  # inside the notch
    assert not c.point_free((7.5, 5))  # inside the material
    assert c.segment_free((1, 5), (6.5, 5))  # into the notch through its opening
    assert not c.segment_free((5, 5), (10, 5))  # through the closed side


def test_robot_radius_inflates_obstacles():
    obstacles = [Rectangle((5, 5), (2, 2)), Circle((10, 5), 1)]
    c = CollisionChecker(obstacles, BOUNDS, robot_radius=0.6)
    assert not c.point_free((3.5, 5))  # 0.5 from the rectangle
    assert c.point_free((3.3, 5))  # 0.7 from the rectangle
    assert not c.point_free((10, 6.5))  # 0.5 from the circle
    assert not c.point_free((0.5, 5))  # 0.5 from the wall
    assert c.segment_free((0.7, 7), (19, 7))
    assert not c.segment_free((0.7, 6.5), (9, 6.5))  # passes 0.5 above the rectangle


def test_segments_vectorized_matches_scalar():
    rng = np.random.default_rng(1)
    c = CollisionChecker([U_SHAPE, Circle((14, 5), 2), Rectangle((16, 2), (3, 1), 30)], BOUNDS, 0.3)
    a = rng.uniform([0, 0], [20, 10], size=(300, 2))
    b = a + rng.normal(0, 3, size=(300, 2))
    batch = c.segments_free(a, b)
    assert batch.tolist() == [c.segment_free(p, q) for p, q in zip(a, b, strict=True)]


@pytest.mark.parametrize("radius", [0.0, 0.4])
def test_exact_segments_agree_with_dense_sampling(radius):
    """Property: a segment reported free never contains a colliding sample point."""
    rng = np.random.default_rng(2)
    obstacles = [U_SHAPE, Circle((14, 5), 2), Rectangle((16, 2), (3, 1), 30)]
    c = CollisionChecker(obstacles, BOUNDS, robot_radius=radius)
    a = rng.uniform([0, 0], [20, 10], size=(400, 2))
    b = a + rng.normal(0, 4, size=(400, 2))
    t = np.linspace(0, 1, 200)
    for p, q, free in zip(a, b, c.segments_free(a, b), strict=True):
        samples_free = c.points_free(p + t[:, None] * (q - p))
        if free:
            assert samples_free.all()
        elif samples_free.all():
            # Only near-tangent cases may be missed by sampling; the exact check is stricter.
            assert c.clearance(p + t[:, None] * (q - p)).min() - radius < 0.05


def test_clearance(checker):
    d = checker.clearance([(1, 1), (5, 5), (5, 7), (10, 7)])
    np.testing.assert_allclose(d, [1, 0, 1, 1], atol=1e-9)


def test_counts_checks(checker):
    before = checker.num_checks
    checker.points_free(np.zeros((7, 2)))
    checker.segments_free(np.zeros((3, 2)), np.ones((3, 2)))
    assert checker.num_checks - before == 10


def test_empty_world():
    c = CollisionChecker([], BOUNDS)
    assert c.point_free((10, 5))
    assert c.segment_free((1, 1), (19, 9))
    assert c.clearance([(10, 5)])[0] == pytest.approx(5)


def test_negative_radius_rejected():
    with pytest.raises(ValueError):
        CollisionChecker([], BOUNDS, robot_radius=-1)
