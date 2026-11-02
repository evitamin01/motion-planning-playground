"""Exact, vectorized collision checking for a disc-shaped robot.

The robot is modelled as a disc of radius ``robot_radius`` (``0`` = point robot)
moving among circles and polygons (rectangles are converted to polygons). The
world boundary acts as a wall. Checks are *exact* in continuous space: a
segment is reported free only if the robot disc swept along it never touches
an obstacle, so paths validated here are guaranteed collision-free.

Queries are batched with NumPy and use an axis-aligned bounding-box broad
phase so that even maps with thousands of obstacle edges stay fast.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .geometry import (
    Circle,
    FloatArray,
    Shape,
    point_segment_distance,
    segment_segment_distance,
    segments_intersect,
)

BoolArray = NDArray[np.bool_]

#: Upper bound on the number of pairwise elements materialized at once.
_CHUNK_ELEMENTS = 400_000


class CollisionChecker:
    """Collision queries for a disc robot in a bounded 2D workspace.

    Args:
        obstacles: Obstacle shapes.
        bounds: Workspace bounds ``(xmin, ymin, xmax, ymax)``.
        robot_radius: Radius of the robot disc; ``0`` for a point robot.
    """

    def __init__(
        self,
        obstacles: Sequence[Shape],
        bounds: tuple[float, float, float, float],
        robot_radius: float = 0.0,
    ) -> None:
        if robot_radius < 0:
            raise ValueError("robot_radius must be non-negative")
        self.bounds = tuple(float(b) for b in bounds)
        self.robot_radius = float(robot_radius)
        r = self.robot_radius
        xmin, ymin, xmax, ymax = self.bounds
        self._inner = (xmin + r, ymin + r, xmax - r, ymax - r)

        circles = [o for o in obstacles if isinstance(o, Circle)]
        self._cc = np.array([c.center for c in circles], dtype=float).reshape(-1, 2)
        self._cr = np.array([c.radius for c in circles], dtype=float) + r

        polys = [o.vertices() for o in obstacles if not isinstance(o, Circle)]
        self._npoly = len(polys)
        if polys:
            self._ea = np.concatenate(polys)
            self._eb = np.concatenate([np.roll(v, -1, axis=0) for v in polys])
            self._edge_poly = np.concatenate(
                [np.full(len(v), i, dtype=np.intp) for i, v in enumerate(polys)]
            )
            self._poly_bb = np.array(
                [
                    [np.min(v[:, 0]), np.min(v[:, 1]), np.max(v[:, 0]), np.max(v[:, 1])]
                    for v in polys
                ]
            )
        else:
            self._ea = self._eb = np.empty((0, 2))
            self._edge_poly = np.empty(0, dtype=np.intp)
            self._poly_bb = np.empty((0, 4))
        # Edge bounding boxes inflated by the robot radius (broad phase).
        self._edge_lo = np.minimum(self._ea, self._eb) - r
        self._edge_hi = np.maximum(self._ea, self._eb) + r

        #: Number of individual point/segment queries answered so far.
        self.num_checks = 0

    # ------------------------------------------------------------------ properties

    @property
    def num_edges(self) -> int:
        return len(self._ea)

    @property
    def num_circles(self) -> int:
        return len(self._cc)

    # ------------------------------------------------------------------ point queries

    def point_free(self, p: ArrayLike) -> bool:
        """Whether the robot placed at ``p`` is collision-free."""
        return bool(self.points_free(np.asarray(p, dtype=float).reshape(1, 2))[0])

    def points_free(self, points: ArrayLike) -> BoolArray:
        """Vectorized :meth:`point_free` for an ``(N, 2)`` array."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        self.num_checks += len(pts)
        free = self._in_bounds(pts)
        for sl in _chunks(len(pts), max(self.num_edges, self.num_circles, 1)):
            free[sl] &= self._points_free_chunk(pts[sl])
        return free

    def _points_free_chunk(self, pts: FloatArray) -> BoolArray:
        free = np.ones(len(pts), dtype=bool)
        if self.num_circles:
            d = np.linalg.norm(pts[:, None, :] - self._cc[None, :, :], axis=-1)
            free &= np.all(d > self._cr[None, :], axis=1)
        if self._npoly:
            free &= ~self._inside_polygons(pts)
            if self.robot_radius > 0:
                si, ei = self._broad_phase(pts, pts)
                if len(si):
                    d = point_segment_distance(pts[si], self._ea[ei], self._eb[ei])
                    hit = np.zeros(len(pts), dtype=bool)
                    hit[si[d <= self.robot_radius]] = True
                    free &= ~hit
        return free

    # ------------------------------------------------------------------ segment queries

    def segment_free(self, a: ArrayLike, b: ArrayLike) -> bool:
        """Whether moving the robot along the straight segment ``a -> b`` is collision-free."""
        a_ = np.asarray(a, dtype=float).reshape(1, 2)
        b_ = np.asarray(b, dtype=float).reshape(1, 2)
        return bool(self.segments_free(a_, b_)[0])

    def segments_free(self, starts: ArrayLike, ends: ArrayLike) -> BoolArray:
        """Vectorized :meth:`segment_free` for ``(N, 2)`` arrays of start and end points."""
        a = np.asarray(starts, dtype=float).reshape(-1, 2)
        b = np.asarray(ends, dtype=float).reshape(-1, 2)
        if a.shape != b.shape:
            raise ValueError("starts and ends must have the same shape")
        self.num_checks += len(a)
        # The free region inside the bounds is convex, so checking endpoints suffices.
        free = self._in_bounds(a) & self._in_bounds(b)
        for sl in _chunks(len(a), max(self.num_edges, self.num_circles, 1)):
            free[sl] &= self._segments_free_chunk(a[sl], b[sl])
        return free

    def _segments_free_chunk(self, a: FloatArray, b: FloatArray) -> BoolArray:
        free = np.ones(len(a), dtype=bool)
        if self.num_circles:
            d = point_segment_distance(self._cc[None, :, :], a[:, None, :], b[:, None, :])
            free &= np.all(d > self._cr[None, :], axis=1)
        if self._npoly:
            si, ei = self._broad_phase(a, b)
            if len(si):
                if self.robot_radius > 0:
                    d = segment_segment_distance(a[si], b[si], self._ea[ei], self._eb[ei])
                    hits = d <= self.robot_radius
                else:
                    hits = segments_intersect(a[si], b[si], self._ea[ei], self._eb[ei])
                hit = np.zeros(len(a), dtype=bool)
                hit[si[hits]] = True
                free &= ~hit
            # A segment that crosses no edge is either entirely inside or outside each polygon.
            free &= ~self._inside_polygons(a)
        return free

    # ------------------------------------------------------------------ distances

    def clearance(self, points: ArrayLike) -> FloatArray:
        """Distance from each point to the nearest obstacle surface or wall (``0`` inside).

        The robot radius is *not* subtracted.
        """
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        xmin, ymin, xmax, ymax = self.bounds
        dist = np.min(
            np.stack([pts[:, 0] - xmin, xmax - pts[:, 0], pts[:, 1] - ymin, ymax - pts[:, 1]]),
            axis=0,
        )
        dist = np.maximum(dist, 0.0)
        for sl in _chunks(len(pts), max(self.num_edges, self.num_circles, 1)):
            p = pts[sl]
            if self.num_circles:
                radii = self._cr - self.robot_radius
                dc = np.linalg.norm(p[:, None, :] - self._cc[None], axis=-1) - radii[None, :]
                dist[sl] = np.minimum(dist[sl], np.maximum(dc.min(axis=1), 0.0))
            if self._npoly:
                de = point_segment_distance(p[:, None, :], self._ea[None], self._eb[None])
                dp = de.min(axis=1)
                dp[self._inside_polygons(p)] = 0.0
                dist[sl] = np.minimum(dist[sl], dp)
        return dist

    # ------------------------------------------------------------------ internals

    def _in_bounds(self, pts: FloatArray) -> BoolArray:
        xmin, ymin, xmax, ymax = self._inner
        return np.asarray(
            (pts[:, 0] >= xmin) & (pts[:, 0] <= xmax) & (pts[:, 1] >= ymin) & (pts[:, 1] <= ymax)
        )

    def _broad_phase(
        self, a: FloatArray, b: FloatArray
    ) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
        """Index pairs (segment, edge) whose inflated bounding boxes overlap."""
        lo = np.minimum(a, b)
        hi = np.maximum(a, b)
        mask = (
            (lo[:, None, 0] <= self._edge_hi[None, :, 0])
            & (hi[:, None, 0] >= self._edge_lo[None, :, 0])
            & (lo[:, None, 1] <= self._edge_hi[None, :, 1])
            & (hi[:, None, 1] >= self._edge_lo[None, :, 1])
        )
        si, ei = np.nonzero(mask)
        return si, ei

    def _inside_polygons(self, pts: FloatArray) -> BoolArray:
        """Whether each point lies strictly inside any polygon (even-odd rule)."""
        n = len(pts)
        if not self._npoly or n == 0:
            return np.zeros(n, dtype=bool)
        px, py = pts[:, 0], pts[:, 1]
        bb = self._poly_bb
        in_bb = (
            (px[:, None] >= bb[None, :, 0])
            & (px[:, None] <= bb[None, :, 2])
            & (py[:, None] >= bb[None, :, 1])
            & (py[:, None] <= bb[None, :, 3])
        )
        if not in_bb.any():
            return np.zeros(n, dtype=bool)
        pi, ei = np.nonzero(in_bb[:, self._edge_poly])
        ax, ay = self._ea[ei, 0], self._ea[ei, 1]
        bx, by = self._eb[ei, 0], self._eb[ei, 1]
        x, y = px[pi], py[pi]
        straddles = (ay > y) != (by > y)
        dy = np.where(straddles, by - ay, 1.0)
        x_cross = ax + (bx - ax) * (y - ay) / dy
        crossing = straddles & (x < x_cross)
        flat = pi[crossing] * self._npoly + self._edge_poly[ei[crossing]]
        counts = np.bincount(flat, minlength=n * self._npoly).reshape(n, self._npoly)
        return np.asarray(np.any(counts % 2 == 1, axis=1))


def _chunks(n: int, width: int) -> list[slice]:
    size = max(1, _CHUNK_ELEMENTS // max(width, 1))
    return [slice(i, min(i + size, n)) for i in range(0, n, size)] or [slice(0, 0)]
