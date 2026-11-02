"""Path post-processing."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .collision import CollisionChecker
from .geometry import Point


def dedupe(path: Sequence[Sequence[float]], tol: float = 1e-9) -> list[Point]:
    """Remove consecutive duplicate waypoints."""
    out: list[Point] = []
    for p in path:
        q = (float(p[0]), float(p[1]))
        if not out or abs(out[-1][0] - q[0]) > tol or abs(out[-1][1] - q[1]) > tol:
            out.append(q)
    if len(out) == 1 and len(path) > 1:
        out.append(out[0])
    return out


def shortcut(path: Sequence[Point], checker: CollisionChecker) -> list[Point]:
    """Greedy shortcutting: from each waypoint jump to the farthest directly reachable one.

    Deterministic, never increases path length, and keeps the path
    collision-free (each new segment is checked exactly).
    """
    pts = np.asarray(path, dtype=float)
    if len(pts) < 3:
        return [tuple(p) for p in pts.tolist()]
    out = [0]
    i = 0
    while i < len(pts) - 1:
        candidates = np.arange(len(pts) - 1, i, -1)
        free = checker.segments_free(np.broadcast_to(pts[i], (len(candidates), 2)), pts[candidates])
        # Adjacent waypoints are connected by the original (valid) path segment.
        free[-1] = True
        j = int(candidates[int(np.argmax(free))])
        out.append(j)
        i = j
    return [(float(pts[k, 0]), float(pts[k, 1])) for k in out]
