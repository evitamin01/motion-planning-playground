"""Artificial potential field planning (a reactive, local method)."""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..collision import CollisionChecker
from ..environment import Problem
from ..geometry import FloatArray, Point
from ..params import ParamsBase, param
from ..trace import Recorder
from .base import Planner, PlanOutcome, register_planner

#: Approximate number of heatmap cells along the longer side of the map.
HEATMAP_CELLS = 140


@register_planner
class PotentialField(Planner):
    name = "potential_field"
    label = "Potential Field"
    family = "Reactive"
    summary = (
        "Follows the gradient of an attractive goal potential plus repulsive obstacle potentials."
    )
    description = """
The robot is treated as a particle in a field of forces: the goal attracts it
and obstacles repel it. The attractive potential grows with the distance to
the goal; each obstacle adds a repulsive potential that is infinite at its
surface and vanishes beyond an influence distance. The robot simply descends
the gradient of the total potential, one small step at a time.

This is extremely cheap and reactive, but it is a local method: wherever the
forces cancel out the robot gets stuck in a local minimum - for example inside
a U-shaped obstacle that faces the goal (try the "Bug trap" scenario). The
random-walk option escapes some minima by taking random steps when progress
stalls. The heatmap shows the potential (darker is lower).
"""
    properties = {
        "Complete": "No (local minima)",
        "Optimal": "No",
        "Space": "Continuous",
    }
    references = [
        "O. Khatib, 'Real-time obstacle avoidance for manipulators and mobile robots', IJRR, 1986.",
        "J. Barraquand, J.-C. Latombe, 'Robot motion planning: A distributed representation "
        "approach', IJRR, 1991.",
    ]
    stochastic = True

    @dataclass
    class Params(ParamsBase):
        attractive_gain: float = param(
            1.0,
            min=0.01,
            max=100.0,
            step=0.1,
            label="Attractive gain",
            help="Strength of the pull towards the goal (conic potential k * distance).",
        )
        repulsive_gain: float = param(
            50.0,
            min=0.0,
            max=10_000.0,
            step=1.0,
            label="Repulsive gain",
            help="Strength of the push away from obstacles.",
        )
        influence_distance: float = param(
            5.0,
            min=0.1,
            max=100.0,
            step=0.1,
            label="Influence distance",
            help="Obstacles farther away than this have no effect.",
        )
        step_size: float = param(
            0.5, min=0.01, max=10.0, step=0.05, label="Step size", help="Gradient descent step."
        )
        max_iterations: int = param(
            2000, min=10, max=50_000, step=100, label="Max iterations", help="Step budget."
        )
        random_walk: bool = param(
            False,
            label="Escape with random walks",
            help="When progress stalls, take a burst of random steps (randomized potential field).",
        )
        walk_steps: int = param(
            25,
            min=1,
            max=500,
            step=1,
            label="Random-walk length",
            help="Number of random steps per escape attempt.",
            advanced=True,
        )

    # ------------------------------------------------------------------ potentials

    def potential(self, checker: CollisionChecker, goal: FloatArray, pts: FloatArray) -> FloatArray:
        """Total potential at ``pts`` (``(N, 2)``); ``inf`` in collision."""
        p = self.params
        rho = checker.clearance(pts) - checker.robot_radius
        u_att = p.attractive_gain * np.linalg.norm(pts - goal, axis=1)
        with np.errstate(divide="ignore"):
            inv = np.where(rho > 0, 1.0 / np.maximum(rho, 1e-12), np.inf)
        rep = np.where(
            rho < p.influence_distance,
            0.5 * p.repulsive_gain * (inv - 1.0 / p.influence_distance) ** 2,
            0.0,
        )
        return np.asarray(u_att + rep)

    def gradient(self, checker: CollisionChecker, goal: FloatArray, x: FloatArray) -> FloatArray:
        h = 1e-3 * max(self.params.step_size, 1e-3)
        dx = np.array([h, 0.0])
        dy = np.array([0.0, h])
        probes = np.array([x + dx, x - dx, x + dy, x - dy])
        u = self.potential(checker, goal, probes)
        if not np.all(np.isfinite(u)):
            # Too close to an obstacle for central differences: push straight away.
            u = np.where(np.isfinite(u), u, 1e12)
        return np.array([(u[0] - u[1]) / (2 * h), (u[2] - u[3]) / (2 * h)])

    def heatmap(self, checker: CollisionChecker, goal: FloatArray) -> dict[str, Any]:
        xmin, ymin, xmax, ymax = checker.bounds
        res = max(xmax - xmin, ymax - ymin) / HEATMAP_CELLS
        nx = max(1, math.ceil((xmax - xmin) / res))
        ny = max(1, math.ceil((ymax - ymin) / res))
        xs = xmin + (np.arange(nx) + 0.5) * res
        ys = ymin + (np.arange(ny) + 0.5) * res
        gx, gy = np.meshgrid(xs, ys)  # row-major: index = j * nx + i
        u = self.potential(checker, goal, np.column_stack([gx.ravel(), gy.ravel()]))
        finite = np.isfinite(u)
        lo = float(np.min(u[finite])) if finite.any() else 0.0
        hi = float(np.percentile(u[finite], 97)) if finite.any() else 1.0
        scaled = np.clip((u - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
        scaled = np.sqrt(scaled)  # spread out the low end where the robot moves
        scaled[~finite] = 1.0
        values = (scaled * 255).astype(np.uint8)
        return {
            "type": "heatmap",
            "label": "Potential",
            "origin": [xmin, ymin],
            "resolution": res,
            "shape": [nx, ny],
            "values": base64.b64encode(values.tobytes()).decode("ascii"),
        }

    # ------------------------------------------------------------------ planning

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker
        goal = np.asarray(problem.goal, dtype=float)
        x = np.asarray(problem.start, dtype=float)
        u_x = float(self.potential(checker, goal, x[None])[0])
        path: list[Point] = [problem.start]
        overlays = [self.heatmap(checker, goal)] if rec.enabled else []
        window = max(10, int(2 * p.influence_distance / p.step_size))
        window_start = 0
        escapes = 0
        stalls = 0

        def advance(x_new: FloatArray) -> None:
            rec.step()
            rec.edge(len(path), path[-1], x_new, "trajectory")
            path.append((float(x_new[0]), float(x_new[1])))

        def stats() -> dict[str, float | int]:
            return {"iterations": it, "escapes": escapes, "stalls": stalls}

        it = 0
        while it < p.max_iterations:
            it += 1
            if np.linalg.norm(goal - x) <= p.step_size and checker.segment_free(x, goal):
                advance(goal)
                return PlanOutcome(path, "", stats(), overlays=overlays)

            # Gradient descent with backtracking: only accept steps that lower the potential.
            grad = self.gradient(checker, goal, x)
            norm = float(np.hypot(grad[0], grad[1]))
            moved = False
            if norm > 1e-12:
                step = p.step_size
                while step >= p.step_size / 32:
                    x_new = x - grad / norm * step
                    if checker.segment_free(x, x_new):
                        u_new = float(self.potential(checker, goal, x_new[None])[0])
                        if u_new < u_x - 1e-9:
                            x, u_x = x_new, u_new
                            advance(x)
                            moved = True
                            break
                    step /= 2

            # A local minimum: no descent step exists, or we are creeping without progress.
            stalled = not moved
            if moved and len(path) - window_start > window:
                stalled = math.dist(path[-1], path[-window]) < 2 * p.step_size
            if not stalled:
                continue
            stalls += 1
            if not p.random_walk:
                return PlanOutcome(
                    None,
                    "Trapped in a local minimum of the potential field. "
                    "Try enabling random-walk escapes or a global planner.",
                    stats(),
                    overlays=overlays,
                )
            escapes += 1
            for _ in range(p.walk_steps):
                for _attempt in range(8):
                    angle = rng.uniform(0, 2 * math.pi)
                    x_new = x + p.step_size * np.array([math.cos(angle), math.sin(angle)])
                    if checker.segment_free(x, x_new):
                        x = x_new
                        advance(x)
                        break
                it += 1
            u_x = float(self.potential(checker, goal, x[None])[0])
            window_start = len(path)

        return PlanOutcome(
            None,
            f"Goal not reached within {p.max_iterations} iterations.",
            stats(),
            overlays=overlays,
        )
