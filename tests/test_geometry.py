from __future__ import annotations

import math

import numpy as np
import pytest

from mpplay.geometry import (
    Circle,
    Polygon,
    Rectangle,
    path_length,
    point_segment_distance,
    polygon_area,
    segment_segment_distance,
    segments_intersect,
    shape_from_dict,
)


def test_rectangle_vertices_axis_aligned():
    r = Rectangle((5, 5), (4, 2))
    v = r.vertices()
    assert v.shape == (4, 2)
    np.testing.assert_allclose(v.min(axis=0), [3, 4])
    np.testing.assert_allclose(v.max(axis=0), [7, 6])
    assert polygon_area(v) == pytest.approx(8.0)  # counter-clockwise


def test_rectangle_rotation_preserves_area_and_center():
    r = Rectangle((1, 2), (4, 2), angle=30)
    v = r.vertices()
    assert abs(polygon_area(v)) == pytest.approx(8.0)
    np.testing.assert_allclose(v.mean(axis=0), [1, 2])
    r90 = Rectangle((0, 0), (4, 2), angle=90)
    xmin, ymin, xmax, ymax = r90.bbox()
    assert (xmax - xmin, ymax - ymin) == (pytest.approx(2), pytest.approx(4))


def test_from_bounds():
    r = Rectangle.from_bounds(3, 1, 1, 5)
    assert r.center == (2, 3)
    assert r.size == (2, 4)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Circle((0, 0), 0),
        lambda: Circle((0, 0), -1),
        lambda: Rectangle((0, 0), (0, 1)),
        lambda: Polygon(((0, 0), (1, 1))),
        lambda: Polygon(((0, 0), (1, 1), (2, 2))),  # collinear -> zero area
        lambda: Circle((math.nan, 0), 1),
    ],
)
def test_invalid_shapes_raise(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "shape",
    [Circle((1, 2), 3), Rectangle((1, 2), (3, 4), 15), Polygon(((0, 0), (4, 0), (2, 3)))],
)
def test_shape_roundtrip(shape):
    assert shape_from_dict(shape.to_dict()) == shape


def test_unknown_shape_type():
    with pytest.raises(ValueError, match="unknown obstacle type"):
        shape_from_dict({"type": "ellipse"})


def test_point_segment_distance():
    a, b = np.array([0.0, 0.0]), np.array([10.0, 0.0])
    assert point_segment_distance(np.array([5.0, 3.0]), a, b) == pytest.approx(3)
    assert point_segment_distance(np.array([-3.0, 4.0]), a, b) == pytest.approx(5)
    # Degenerate segment.
    assert point_segment_distance(np.array([3.0, 4.0]), a, a) == pytest.approx(5)


@pytest.mark.parametrize(
    ("seg1", "seg2", "expected"),
    [
        (((0, 0), (2, 2)), ((0, 2), (2, 0)), True),  # crossing
        (((0, 0), (2, 0)), ((2, 0), (3, 1)), True),  # touching at endpoint
        (((0, 0), (2, 0)), ((1, 0), (3, 0)), True),  # collinear overlap
        (((0, 0), (1, 0)), ((2, 0), (3, 0)), False),  # collinear disjoint
        (((0, 0), (2, 0)), ((0, 1), (2, 1)), False),  # parallel
        (((0, 0), (2, 0)), ((1, 0.5), (1, 3)), False),  # T, not reaching
        (((0, 0), (2, 0)), ((1, 0), (1, 3)), True),  # T, touching
    ],
)
def test_segments_intersect(seg1, seg2, expected):
    a, b = (np.asarray(p, dtype=float) for p in seg1)
    c, d = (np.asarray(p, dtype=float) for p in seg2)
    assert bool(segments_intersect(a, b, c, d)) is expected
    assert bool(segments_intersect(c, d, a, b)) is expected


def test_segment_segment_distance():
    a, b = np.array([0.0, 0.0]), np.array([2.0, 0.0])
    c, d = np.array([0.0, 1.5]), np.array([2.0, 3.0])
    assert segment_segment_distance(a, b, c, d) == pytest.approx(1.5)
    assert segment_segment_distance(a, b, np.array([1.0, -1.0]), np.array([1.0, 1.0])) == 0


def test_path_length():
    assert path_length([(0, 0), (3, 4), (3, 0)]) == pytest.approx(9)
    assert path_length([(1, 1)]) == 0
