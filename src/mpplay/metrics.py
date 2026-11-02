"""Path quality metrics shared by all planners."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from .collision import CollisionChecker
from .geometry import FloatArray

#: Maximum number of points sampled along a path to estimate clearance.
MAX_CLEARANCE_SAMPLES = 2000

#: Metric metadata used by the UI and reports: (key, label, unit, lower_is_better).
METRICS: list[tuple[str, str, str, bool]] = [
    ("path_length", "Path length", "", True),
    ("planning_time_ms", "Planning time", "ms", True),
    ("waypoints", "Waypoints", "", True),
    ("turning_deg", "Total turning", "deg", True),
    ("max_turn_deg", "Sharpest turn", "deg", True),
    ("min_clearance", "Min. clearance", "", False),
    ("collision_checks", "Collision checks", "", True),
]


def resample(path: FloatArray, spacing: float) -> FloatArray:
    """Points along a polyline at roughly uniform ``spacing`` (including all vertices)."""
    out = [path[:1]]
    for a, b in pairwise(path):
        n = max(1, math.ceil(float(np.linalg.norm(b - a)) / spacing))
        t = np.linspace(0.0, 1.0, n + 1)[1:, None]
        out.append(a + t * (b - a))
    return np.concatenate(out)


def turning_angles(path: FloatArray) -> FloatArray:
    """Absolute heading changes (radians) at the interior vertices of a path."""
    if len(path) < 3:
        return np.zeros(0)
    seg = np.diff(path, axis=0)
    seg = seg[np.linalg.norm(seg, axis=1) > 1e-12]
    if len(seg) < 2:
        return np.zeros(0)
    heading = np.arctan2(seg[:, 1], seg[:, 0])
    turn = np.diff(heading)
    return np.abs((turn + np.pi) % (2 * np.pi) - np.pi)


def compute_metrics(path: Sequence[Sequence[float]], checker: CollisionChecker) -> dict[str, Any]:
    """Length, smoothness and clearance of a path."""
    pts = np.asarray(path, dtype=float)
    length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if len(pts) > 1 else 0.0
    turns = turning_angles(pts)
    spacing = max(length / MAX_CLEARANCE_SAMPLES, 1e-6) if length > 0 else 1.0
    samples = resample(pts, spacing) if len(pts) > 1 else pts
    clearance = float(np.min(checker.clearance(samples)) - checker.robot_radius)
    return {
        "path_length": round(length, 4),
        "waypoints": len(pts),
        "turning_deg": round(math.degrees(float(turns.sum())), 2),
        "max_turn_deg": round(math.degrees(float(np.max(turns))) if len(turns) else 0.0, 2),
        "min_clearance": round(max(clearance, 0.0), 4),
    }
