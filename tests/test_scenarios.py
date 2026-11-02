from __future__ import annotations

import pytest

from mpplay.environment import Environment, Problem
from mpplay.runner import run_planner
from mpplay.scenarios import GENERATORS, SCENARIOS, get_scenario


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_is_valid(name):
    env = get_scenario(name)
    assert env.name and env.description
    checker = Problem(env).checker
    assert checker.point_free(env.start)
    assert checker.point_free(env.goal)
    assert Environment.from_dict(env.to_dict()) == env
    assert Environment.from_json(env.to_json()) == env


def test_unknown_scenario():
    with pytest.raises(KeyError, match="unknown scenario"):
        get_scenario("atlantis")


@pytest.mark.parametrize("name", list(GENERATORS))
def test_generators_are_deterministic(name):
    gen = GENERATORS[name]
    a = gen.generate(seed=11)
    b = gen.generate(seed=11)
    c = gen.generate(seed=12)
    assert a == b
    assert a != c
    checker = Problem(a).checker
    assert checker.point_free(a.start) and checker.point_free(a.goal)


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("braid", [0.0, 0.5])
def test_mazes_are_solvable(seed, braid):
    env = GENERATORS["maze"].generate({"cols": 8, "rows": 5, "braid": braid}, seed=seed)
    assert run_planner(env, "bfs", trace=False).success


def test_braiding_removes_walls():
    perfect = GENERATORS["maze"].generate({"braid": 0.0}, seed=1)
    braided = GENERATORS["maze"].generate({"braid": 1.0}, seed=1)
    wall_area = lambda env: sum(o.size[0] * o.size[1] for o in env.obstacles)  # noqa: E731
    assert wall_area(braided) < wall_area(perfect)


def test_generator_params_validated():
    with pytest.raises(ValueError):
        GENERATORS["forest"].generate({"count": -3})


def test_environment_validation():
    with pytest.raises(ValueError):
        Environment(bounds=(0, 0, -1, 1), start=(0, 0), goal=(0, 0))
    with pytest.raises(ValueError):
        Environment(bounds=(0, 0, 1, 1), start=(0, 0), goal=(0, 0), resolution=0)
    with pytest.raises(ValueError, match="missing required field"):
        Environment.from_dict({"bounds": [0, 0, 1, 1]})
    with pytest.raises(ValueError, match="unsupported"):
        Environment.from_dict(
            {"version": 99, "bounds": [0, 0, 1, 1], "start": [0, 0], "goal": [1, 1]}
        )


def test_save_and_load(tmp_path):
    env = get_scenario("office")
    path = tmp_path / "office.json"
    env.save(path)
    assert Environment.load(path) == env
