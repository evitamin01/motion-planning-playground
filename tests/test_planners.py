from __future__ import annotations

import math

import numpy as np
import pytest

from mpplay.environment import Environment, Problem
from mpplay.planners import available_planners, get_planner
from mpplay.runner import run_planner
from mpplay.scenarios import SCENARIOS
from mpplay.trace import TraceState

ALL_PLANNERS = [p.name for p in available_planners()]
COMPLETE_PLANNERS = [p for p in ALL_PLANNERS if p != "potential_field"]
GRID_PLANNERS = [p.name for p in available_planners() if p.uses_grid]

# Keep the test suite fast: smaller budgets for the anytime planners.
FAST_PARAMS = {
    "rrt_star": {"max_iterations": 1500},
    "informed_rrt_star": {"max_iterations": 1500},
}

# Narrow passages are hard for sampling: give those planners more budget there.
HARD_PARAMS = {
    "rrt": {"max_iterations": 20000},
    "rrt_connect": {"max_iterations": 20000},
    "rrt_star": {"max_iterations": 4000},
    "informed_rrt_star": {"max_iterations": 4000},
    "prm": {"num_samples": 2500},
}


@pytest.fixture(scope="module")
def problems() -> dict[str, Problem]:
    return {name: Problem(s.build()) for name, s in SCENARIOS.items()}


def assert_valid_path(result, env: Environment) -> None:
    assert result.success, result.message
    path = np.asarray(result.path)
    np.testing.assert_allclose(path[0], env.start)
    np.testing.assert_allclose(path[-1], env.goal)
    checker = Problem(env).checker
    assert checker.segments_free(path[:-1], path[1:]).all()
    assert result.metrics["path_length"] >= math.dist(env.start, env.goal) - 1e-6


def test_registry_lists_builtin_planners():
    expected = {
        "bfs",
        "dijkstra",
        "astar",
        "greedy",
        "theta_star",
        "rrt",
        "rrt_connect",
        "rrt_star",
        "informed_rrt_star",
        "prm",
        "potential_field",
    }
    assert expected <= set(ALL_PLANNERS)
    with pytest.raises(KeyError, match="unknown planner"):
        get_planner("nope")


@pytest.mark.parametrize("planner", ALL_PLANNERS)
def test_planner_info_is_complete(planner):
    info = get_planner(planner).info()
    assert info["label"] and info["summary"] and info["description"]
    assert info["properties"] and info["references"]
    for spec in info["params"]:
        assert spec["label"] and "default" in spec


@pytest.mark.parametrize("planner", COMPLETE_PLANNERS)
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_complete_planners_solve_every_scenario(planner, scenario, problems):
    if scenario == "narrow_passage":
        params = HARD_PARAMS.get(planner, {})
    elif scenario in {"maze", "office"}:
        params = {}  # winding routes need the default budgets
    else:
        params = FAST_PARAMS.get(planner, {})
    result = run_planner(
        problems[scenario], planner, params, seed=3, trace=False, raise_errors=True
    )
    assert_valid_path(result, problems[scenario].env)


@pytest.mark.parametrize("scenario", ["open_field", "slalom"])
def test_potential_field_succeeds_in_simple_worlds(scenario, problems):
    result = run_planner(problems[scenario], "potential_field", seed=0, raise_errors=True)
    assert_valid_path(result, problems[scenario].env)
    assert result.overlays and result.overlays[0]["type"] == "heatmap"


def test_potential_field_gets_trapped(problems):
    result = run_planner(problems["bug_trap"], "potential_field", seed=0, raise_errors=True)
    assert not result.success
    assert "local minimum" in result.message


def test_potential_field_random_walk_runs(problems):
    result = run_planner(
        problems["bug_trap"],
        "potential_field",
        {"random_walk": True, "max_iterations": 3000},
        seed=1,
        trace=False,
        raise_errors=True,
    )
    assert result.stats["escapes"] >= 1


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_astar_matches_dijkstra(scenario, problems):
    a = run_planner(problems[scenario], "astar", trace=False)
    d = run_planner(problems[scenario], "dijkstra", trace=False)
    assert a.metrics["path_length"] == pytest.approx(d.metrics["path_length"])
    assert a.stats["expansions"] <= d.stats["expansions"]


@pytest.mark.parametrize("weight", [1.5, 3.0])
def test_weighted_astar_bound(weight, problems):
    p = problems["scattered"]
    opt = run_planner(p, "astar", trace=False).metrics["path_length"]
    w = run_planner(p, "astar", {"weight": weight}, trace=False).metrics["path_length"]
    # Grid path costs exclude the short hops to the exact start/goal points.
    assert opt - 1e-9 <= w <= weight * opt + 2 * p.env.resolution


def test_four_connectivity_is_longer(problems):
    p = problems["open_field"]
    four = run_planner(p, "astar", {"connectivity": "4"}, trace=False)
    eight = run_planner(p, "astar", {"connectivity": "8"}, trace=False)
    assert four.success and eight.success
    assert four.metrics["turning_deg"] % 90 == pytest.approx(0)
    assert four.metrics["path_length"] >= eight.metrics["path_length"] - 1e-9


def test_theta_star_is_any_angle(problems):
    p = problems["scattered"]
    theta = run_planner(p, "theta_star", trace=False)
    astar = run_planner(p, "astar", trace=False)
    assert theta.metrics["path_length"] < astar.metrics["path_length"]
    assert theta.metrics["waypoints"] < astar.metrics["waypoints"]
    eager = run_planner(p, "theta_star", {"lazy": False}, trace=False)
    assert eager.success


@pytest.mark.parametrize("planner", [*GRID_PLANNERS, "rrt", "rrt_connect", "prm"])
def test_unreachable_goal_fails_cleanly(planner, blocked_env):
    params = {"max_iterations": 300} if planner.startswith("rrt") else {}
    if planner == "prm":
        params = {"num_samples": 200}
    result = run_planner(blocked_env, planner, params, trace=False, raise_errors=True)
    assert not result.success
    assert result.message
    assert result.path is None


def test_start_in_collision(wall_env):
    env = wall_env.with_changes(start=(10, 3))
    result = run_planner(env, "astar")
    assert not result.success
    assert "start" in result.message


def test_start_in_conservatively_blocked_cell(wall_env):
    # Free in continuous space but its grid cell touches the wall.
    env = wall_env.with_changes(start=(8.9, 2))
    assert Problem(env).checker.point_free(env.start)
    result = run_planner(env, "astar")
    assert not result.success
    assert "occupied grid cell" in result.message


@pytest.mark.parametrize("planner", ["rrt", "rrt_connect", "rrt_star", "prm", "potential_field"])
def test_stochastic_planners_are_reproducible(planner, problems):
    p = problems["scattered"]
    params = FAST_PARAMS.get(planner, {})
    a = run_planner(p, planner, params, seed=7, trace=False)
    b = run_planner(p, planner, params, seed=7, trace=False)
    assert a.path == b.path
    if planner in {"rrt", "rrt_connect", "prm"}:
        c = run_planner(p, planner, params, seed=8, trace=False)
        assert c.path != a.path


@pytest.mark.parametrize("planner", ["astar", "dijkstra", "bfs", "greedy"])
def test_grid_trace_matches_stats(planner, problems):
    result = run_planner(problems["bug_trap"], planner)
    state = TraceState.replay(result.trace)
    assert len(state.expanded) == result.stats["expansions"]
    assert result.trace["num_steps"] == result.stats["expansions"]
    assert result.grid is not None


def test_rrt_trace_builds_the_tree(problems):
    result = run_planner(problems["scattered"], "rrt", seed=2)
    state = TraceState.replay(result.trace)
    assert len(state.edges) == result.stats["tree_size"] - 1
    assert result.trace["num_steps"] == result.stats["iterations"]


def test_rrt_star_converges_monotonically(problems):
    result = run_planner(problems["bug_trap"], "rrt_star", {"max_iterations": 2000}, seed=4)
    costs = [c for _, c in result.series["best_cost"]]
    assert costs == sorted(costs, reverse=True)
    assert result.metrics["path_length"] == pytest.approx(costs[-1], abs=1e-3)
    assert result.stats["first_solution_iteration"] <= 2000


def test_informed_rrt_star_emits_ellipse(problems):
    result = run_planner(
        problems["open_field"], "informed_rrt_star", {"max_iterations": 600}, seed=1
    )
    state = TraceState.replay(result.trace)
    assert state.overlays["informed_set"]["type"] == "ellipse"
    straight = math.dist(problems["open_field"].start, problems["open_field"].goal)
    assert result.metrics["path_length"] == pytest.approx(straight, rel=0.02)


def test_prm_trace_has_roadmap(problems):
    result = run_planner(problems["scattered"], "prm", {"num_samples": 300}, seed=0)
    state = TraceState.replay(result.trace)
    assert sum(1 for n in state.nodes if n[2] == "roadmap") == 300
    assert len(state.edges) == result.stats["roadmap_edges"]


def test_robot_radius_increases_clearance(problems):
    env = problems["scattered"].env
    point = run_planner(env, "astar", trace=False)
    disc = run_planner(env.with_changes(robot_radius=1.0), "astar", trace=False)
    assert point.success and disc.success
    assert disc.metrics["path_length"] >= point.metrics["path_length"] - 1e-9


def test_trivial_problem():
    env = Environment(bounds=(0, 0, 10, 10), start=(5, 5), goal=(5.2, 5))
    for planner in ALL_PLANNERS:
        result = run_planner(env, planner, FAST_PARAMS.get(planner), trace=False, raise_errors=True)
        assert result.success, planner
