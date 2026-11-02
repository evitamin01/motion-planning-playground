"""Running planners: timing, validation, smoothing and metrics in one place."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .environment import Environment, Problem
from .geometry import Point
from .metrics import compute_metrics
from .planners import PlanningError, get_planner
from .postprocess import dedupe, shortcut
from .trace import NullRecorder, Recorder

log = logging.getLogger(__name__)


@dataclass
class PlanResult:
    """Outcome of one planner run, ready to be serialized for the UI."""

    planner: str
    label: str
    params: dict[str, Any]
    seed: int
    success: bool
    message: str = ""
    path: list[Point] | None = None
    raw_path: list[Point] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    series: dict[str, list[list[float]]] = field(default_factory=dict)
    trace: dict[str, Any] | None = None
    grid: dict[str, Any] | None = None
    overlays: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "label": self.label,
            "params": self.params,
            "seed": self.seed,
            "success": self.success,
            "message": self.message,
            "path": [list(p) for p in self.path] if self.path else None,
            "raw_path": [list(p) for p in self.raw_path] if self.raw_path else None,
            "metrics": self.metrics,
            "stats": self.stats,
            "series": self.series,
            "trace": self.trace,
            "grid": self.grid,
            "overlays": self.overlays,
        }


def run_planner(
    problem: Problem | Environment,
    planner: str,
    params: Mapping[str, Any] | None = None,
    *,
    seed: int = 0,
    trace: bool = True,
    smoothing: bool = False,
    include_grid: bool | None = None,
    raise_errors: bool = False,
) -> PlanResult:
    """Run one planner on a problem and collect everything needed to display or compare it.

    Args:
        problem: The planning problem (an :class:`Environment` is wrapped automatically).
        planner: Registry name of the planner.
        params: Planner parameters (validated; defaults fill in missing values).
        seed: Seed for the planner's random number generator.
        trace: Record visualization events (disable for benchmarking).
        smoothing: Apply greedy shortcutting to the path.
        include_grid: Attach the occupancy grid (defaults to ``trace`` for grid planners).
        raise_errors: Re-raise unexpected planner exceptions instead of reporting them.
    """
    if isinstance(problem, Environment):
        problem = Problem(problem)
    cls = get_planner(planner)
    instance = cls(params)
    rec: Recorder = Recorder() if trace else NullRecorder()
    result = PlanResult(
        planner=cls.name,
        label=cls.label,
        params=instance.params.to_dict(),
        seed=seed,
        success=False,
    )
    # A dedicated checker per run gives an exact collision-check count even when
    # several runs share a problem concurrently.
    run_problem = problem.fork()
    checker = run_problem.checker

    if not checker.point_free(problem.start):
        result.message = "The start position is in collision."
        return result
    if not checker.point_free(problem.goal):
        result.message = "The goal position is in collision."
        return result

    t0 = time.perf_counter()
    try:
        instance.setup(run_problem)
    except ValueError as exc:  # e.g. the grid would be too large
        result.message = str(exc)
        return result
    try:
        t1 = time.perf_counter()
        checks_before = checker.num_checks
        outcome = instance.plan(run_problem, np.random.default_rng(seed), rec)
        t2 = time.perf_counter()
    except PlanningError as exc:
        result.message = str(exc)
        return result
    except Exception as exc:
        if raise_errors:
            raise
        log.exception("planner %s failed", planner)
        result.message = f"Planner error: {type(exc).__name__}: {exc}"
        return result

    if include_grid is None:
        include_grid = trace and cls.uses_grid
    if include_grid:
        result.grid = run_problem.grid().to_dict()
    result.trace = rec.to_dict() if trace else None
    result.stats = dict(outcome.stats)
    result.series = dict(outcome.series)
    result.overlays = list(outcome.overlays)
    result.message = outcome.message
    result.metrics = {
        "planning_time_ms": round((t2 - t1) * 1000, 3),
        "setup_time_ms": round((t1 - t0) * 1000, 3),
        "collision_checks": checker.num_checks - checks_before,
    }

    if outcome.path is None:
        return result
    path = dedupe(outcome.path)
    error = _validate_path(path, problem)
    if error is None and not bool(np.all(checker.segments_free(path[:-1], path[1:]))):
        error = "the returned path collides with an obstacle"
    if error is not None:
        result.message = f"Invalid path from planner: {error}."
        log.warning("planner %s returned an invalid path: %s", planner, error)
        return result

    if smoothing:
        result.raw_path = path
        path = shortcut(path, checker)
    result.path = path
    result.success = True
    result.metrics.update(compute_metrics(path, checker))
    return result


def _validate_path(path: list[Point], problem: Problem) -> str | None:
    if len(path) < 2:
        return "a path needs at least two waypoints"
    if np.linalg.norm(np.subtract(path[0], problem.start)) > 1e-6:
        return "the path does not begin at the start"
    if np.linalg.norm(np.subtract(path[-1], problem.goal)) > 1e-6:
        return "the path does not end at the goal"
    return None
