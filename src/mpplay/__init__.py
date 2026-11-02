"""Motion Planning Playground: explore, visualize and compare 2D motion planning algorithms.

Quick start::

    from mpplay import get_scenario, run_planner

    env = get_scenario("bug_trap")
    result = run_planner(env, "astar", {"weight": 2.0})
    print(result.success, result.metrics["path_length"])
"""

from __future__ import annotations

__version__ = "0.1.0"

from .benchmark import RunSpec, run_benchmark
from .environment import Environment, Problem
from .geometry import Circle, Polygon, Rectangle
from .params import ParamsBase, param
from .planners import (
    GridPlanner,
    Planner,
    PlanningError,
    PlanOutcome,
    available_planners,
    get_planner,
    register_planner,
)
from .runner import PlanResult, run_planner
from .scenarios import GENERATORS, SCENARIOS, get_scenario
from .trace import Recorder

__all__ = [
    "GENERATORS",
    "SCENARIOS",
    "Circle",
    "Environment",
    "GridPlanner",
    "ParamsBase",
    "PlanOutcome",
    "PlanResult",
    "Planner",
    "PlanningError",
    "Polygon",
    "Problem",
    "Recorder",
    "Rectangle",
    "RunSpec",
    "__version__",
    "available_planners",
    "get_planner",
    "get_scenario",
    "param",
    "register_planner",
    "run_benchmark",
    "run_planner",
]
