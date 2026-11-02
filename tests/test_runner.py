from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from mpplay import Planner, PlanOutcome, register_planner
from mpplay.environment import Problem
from mpplay.params import ParamsBase, param
from mpplay.planners import available_planners, get_planner, unregister_planner
from mpplay.runner import run_planner
from mpplay.trace import NullRecorder, Recorder


@pytest.fixture
def straight_line_planner():
    """A plugin-style planner that ignores obstacles (to exercise path validation)."""

    @register_planner
    class StraightLine(Planner):
        name = "test_straight_line"
        label = "Straight line"
        family = "Test"
        summary = "Connects start and goal directly."

        @dataclass
        class Params(ParamsBase):
            waypoints: int = param(2, min=2, max=10)

        def plan(self, problem, rng, rec):
            pts = np.linspace(problem.start, problem.goal, self.params.waypoints)
            for p in pts:
                rec.step()
                rec.node(p)
            return PlanOutcome([tuple(p) for p in pts], stats={"calls": 1})

    yield StraightLine
    unregister_planner(StraightLine.name)


@pytest.fixture
def crashing_planner():
    @register_planner
    class Crash(Planner):
        name = "test_crash"
        label = "Crash"

        def plan(self, problem, rng, rec):
            raise RuntimeError("boom")

    yield Crash
    unregister_planner(Crash.name)


def test_custom_planner_is_registered(straight_line_planner, empty_env):
    assert straight_line_planner in available_planners()
    assert get_planner("test_straight_line") is straight_line_planner
    result = run_planner(empty_env, "test_straight_line", {"waypoints": 4})
    assert result.success
    assert result.metrics["waypoints"] == 4
    assert result.stats == {"calls": 1}
    assert result.trace["num_steps"] == 4


def test_duplicate_registration_rejected(straight_line_planner):
    with pytest.raises(ValueError, match="already registered"):

        @register_planner
        class Other(Planner):
            name = "test_straight_line"
            label = "Other"

            def plan(self, problem, rng, rec):  # pragma: no cover
                return PlanOutcome(None)


def test_planner_without_name_rejected():
    with pytest.raises(TypeError, match="name"):

        @register_planner
        class Nameless(Planner):
            label = "Nameless"

            def plan(self, problem, rng, rec):  # pragma: no cover
                return PlanOutcome(None)


def test_colliding_path_is_rejected(straight_line_planner, wall_env):
    result = run_planner(wall_env, "test_straight_line")
    assert not result.success
    assert "collides" in result.message
    assert result.path is None


def test_planner_exceptions_are_reported(crashing_planner, empty_env):
    result = run_planner(empty_env, "test_crash")
    assert not result.success
    assert "RuntimeError: boom" in result.message
    with pytest.raises(RuntimeError):
        run_planner(empty_env, "test_crash", raise_errors=True)


def test_invalid_params_raise(empty_env):
    with pytest.raises(ValueError):
        run_planner(empty_env, "astar", {"weight": 0.5})


def test_smoothing_shortens_path(wall_problem):
    raw = run_planner(wall_problem, "rrt", seed=5, trace=False)
    smooth = run_planner(wall_problem, "rrt", seed=5, trace=False, smoothing=True)
    assert smooth.success and smooth.raw_path is not None
    assert smooth.metrics["path_length"] <= raw.metrics["path_length"] + 1e-9
    assert smooth.metrics["waypoints"] <= raw.metrics["waypoints"]
    checker = wall_problem.checker
    p = np.asarray(smooth.path)
    assert checker.segments_free(p[:-1], p[1:]).all()


def test_result_serializes(wall_problem):
    data = run_planner(wall_problem, "astar").to_dict()
    assert data["success"] is True
    assert data["grid"]["shape"] == [40, 20]
    assert data["trace"]["num_steps"] > 0
    assert {"path_length", "planning_time_ms", "collision_checks"} <= set(data["metrics"])


def test_untraced_run_has_no_trace(wall_problem):
    data = run_planner(wall_problem, "rrt", trace=False).to_dict()
    assert data["trace"] is None and data["grid"] is None


def test_collision_checks_are_counted_per_run(wall_problem):
    a = run_planner(wall_problem, "rrt", seed=1, trace=False)
    b = run_planner(wall_problem, "rrt", seed=1, trace=False)
    assert a.metrics["collision_checks"] == b.metrics["collision_checks"] > 0


def test_recorder_truncates():
    rec = Recorder(max_events=5)
    for i in range(10):
        rec.step()
        rec.expand(i, i)
    data = rec.to_dict()
    assert data["truncated"] is True
    assert len(data["events"]) == 5


def test_null_recorder_records_nothing():
    rec = NullRecorder()
    rec.step()
    rec.edge(1, (0, 0), (1, 1))
    assert rec.events == [] and not rec.enabled


def test_problem_fork_shares_grid(wall_problem):
    fork = wall_problem.fork()
    assert fork.checker is not wall_problem.checker
    assert fork.grid() is wall_problem.grid()
    assert isinstance(fork, Problem)
