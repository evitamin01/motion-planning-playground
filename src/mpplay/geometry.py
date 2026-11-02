"""Obstacle shapes and small vectorized geometry helpers.

All coordinates are expressed in world units with the y axis pointing up.
Shapes are immutable value objects that can be (de)serialized to plain JSON
dictionaries, which is the format used by the web UI and scenario files.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Point = tuple[float, float]


def _point(value: Sequence[float]) -> Point:
    if len(value) != 2:
        raise ValueError(f"expected a 2D point, got {value!r}")
    x, y = float(value[0]), float(value[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"point coordinates must be finite, got {value!r}")
    return (x, y)


@dataclass(frozen=True)
class Circle:
    """A disc obstacle."""

    center: Point
    radius: float

    kind: ClassVar[str] = "circle"

    def __post_init__(self) -> None:
        object.__setattr__(self, "center", _point(self.center))
        if not self.radius > 0:
            raise ValueError("circle radius must be positive")
        object.__setattr__(self, "radius", float(self.radius))

    def bbox(self) -> tuple[float, float, float, float]:
        cx, cy = self.center
        r = self.radius
        return (cx - r, cy - r, cx + r, cy + r)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "center": list(self.center), "radius": self.radius}


@dataclass(frozen=True)
class Rectangle:
    """A (possibly rotated) rectangle given by its center, size and angle in degrees."""

    center: Point
    size: Point
    angle: float = 0.0

    kind: ClassVar[str] = "rect"

    def __post_init__(self) -> None:
        object.__setattr__(self, "center", _point(self.center))
        size = _point(self.size)
        if size[0] <= 0 or size[1] <= 0:
            raise ValueError("rectangle width and height must be positive")
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "angle", float(self.angle))

    @classmethod
    def from_bounds(cls, xmin: float, ymin: float, xmax: float, ymax: float) -> Rectangle:
        """Axis-aligned rectangle from its corner coordinates."""
        return cls(((xmin + xmax) / 2, (ymin + ymax) / 2), (abs(xmax - xmin), abs(ymax - ymin)))

    def vertices(self) -> FloatArray:
        """Corners in counter-clockwise order, shape ``(4, 2)``."""
        hw, hh = self.size[0] / 2, self.size[1] / 2
        local = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]], dtype=float)
        theta = math.radians(self.angle)
        c, s = math.cos(theta), math.sin(theta)
        rot = np.array([[c, -s], [s, c]])
        return local @ rot.T + np.asarray(self.center)

    def bbox(self) -> tuple[float, float, float, float]:
        v = self.vertices()
        return (
            float(np.min(v[:, 0])),
            float(np.min(v[:, 1])),
            float(np.max(v[:, 0])),
            float(np.max(v[:, 1])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "center": list(self.center),
            "size": list(self.size),
            "angle": self.angle,
        }


@dataclass(frozen=True)
class Polygon:
    """A simple polygon (convex or concave) given by its vertices."""

    points: tuple[Point, ...]

    kind: ClassVar[str] = "polygon"

    def __post_init__(self) -> None:
        pts = tuple(_point(p) for p in self.points)
        if len(pts) < 3:
            raise ValueError("a polygon needs at least 3 vertices")
        if abs(polygon_area(np.asarray(pts))) < 1e-12:
            raise ValueError("polygon is degenerate (zero area)")
        object.__setattr__(self, "points", pts)

    def vertices(self) -> FloatArray:
        return np.asarray(self.points, dtype=float)

    def bbox(self) -> tuple[float, float, float, float]:
        v = self.vertices()
        return (
            float(np.min(v[:, 0])),
            float(np.min(v[:, 1])),
            float(np.max(v[:, 0])),
            float(np.max(v[:, 1])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "points": [list(p) for p in self.points]}


Shape = Circle | Rectangle | Polygon


def shape_from_dict(data: dict[str, Any]) -> Shape:
    """Parse a shape from its JSON representation."""
    kind = data.get("type")
    if kind == "circle":
        return Circle(center=data["center"], radius=data["radius"])
    if kind == "rect":
        return Rectangle(center=data["center"], size=data["size"], angle=data.get("angle", 0.0))
    if kind == "polygon":
        return Polygon(points=tuple(data["points"]))
    raise ValueError(f"unknown obstacle type {kind!r}")


def polygon_area(vertices: FloatArray) -> float:
    """Signed area (positive for counter-clockwise vertex order)."""
    x, y = vertices[:, 0], vertices[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# --------------------------------------------------------------------------- vector helpers


def cross2(ax: FloatArray, ay: FloatArray, bx: FloatArray, by: FloatArray) -> FloatArray:
    """z-component of the 2D cross product, elementwise."""
    return ax * by - ay * bx


def point_segment_distance(p: FloatArray, a: FloatArray, b: FloatArray) -> FloatArray:
    """Distance between points ``p`` and segments ``ab`` (all broadcastable ``(..., 2)``)."""
    ab = b - a
    ap = p - a
    denom = np.sum(ab * ab, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.where(denom > 0, np.sum(ap * ab, axis=-1) / denom, 0.0)
    t = np.clip(t, 0.0, 1.0)
    closest = a + t[..., None] * ab
    return np.linalg.norm(p - closest, axis=-1)


def segments_intersect(
    a: FloatArray, b: FloatArray, c: FloatArray, d: FloatArray
) -> NDArray[np.bool_]:
    """Whether closed segments ``ab`` and ``cd`` intersect (touching counts), elementwise.

    All inputs broadcast against each other with a trailing dimension of 2.
    """
    eps = 1e-12
    r = b - a
    s = d - c
    d1 = cross2(r[..., 0], r[..., 1], c[..., 0] - a[..., 0], c[..., 1] - a[..., 1])
    d2 = cross2(r[..., 0], r[..., 1], d[..., 0] - a[..., 0], d[..., 1] - a[..., 1])
    d3 = cross2(s[..., 0], s[..., 1], a[..., 0] - c[..., 0], a[..., 1] - c[..., 1])
    d4 = cross2(s[..., 0], s[..., 1], b[..., 0] - c[..., 0], b[..., 1] - c[..., 1])
    proper = (((d1 > eps) & (d2 < -eps)) | ((d1 < -eps) & (d2 > eps))) & (
        ((d3 > eps) & (d4 < -eps)) | ((d3 < -eps) & (d4 > eps))
    )

    def on_segment(p: FloatArray, q: FloatArray, x: FloatArray) -> NDArray[np.bool_]:
        lo = np.minimum(p, q) - eps
        hi = np.maximum(p, q) + eps
        return np.all((x >= lo) & (x <= hi), axis=-1)

    touch = (
        ((np.abs(d1) <= eps) & on_segment(a, b, c))
        | ((np.abs(d2) <= eps) & on_segment(a, b, d))
        | ((np.abs(d3) <= eps) & on_segment(c, d, a))
        | ((np.abs(d4) <= eps) & on_segment(c, d, b))
    )
    return np.asarray(proper | touch)


def segment_segment_distance(
    a: FloatArray, b: FloatArray, c: FloatArray, d: FloatArray
) -> FloatArray:
    """Minimum distance between segments ``ab`` and ``cd``, elementwise."""
    dist = np.minimum(
        np.minimum(point_segment_distance(a, c, d), point_segment_distance(b, c, d)),
        np.minimum(point_segment_distance(c, a, b), point_segment_distance(d, a, b)),
    )
    return np.where(segments_intersect(a, b, c, d), 0.0, dist)


def path_length(path: Iterable[Sequence[float]]) -> float:
    pts = np.asarray(list(path), dtype=float)
    if len(pts) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
