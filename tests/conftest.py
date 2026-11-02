from __future__ import annotations

import os

import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

from mpplay.environment import Environment, Problem
from mpplay.geometry import Rectangle


@pytest.fixture
def empty_env() -> Environment:
    return Environment(bounds=(0, 0, 20, 10), start=(1, 5), goal=(19, 5))


@pytest.fixture
def wall_env() -> Environment:
    """A wall across the middle with a gap at the top."""
    return Environment(
        bounds=(0, 0, 20, 10),
        start=(2, 2),
        goal=(18, 2),
        obstacles=(Rectangle.from_bounds(9, 0, 11, 7),),
        resolution=0.5,
    )


@pytest.fixture
def blocked_env() -> Environment:
    """The goal is enclosed by walls: no path exists."""
    walls = (
        Rectangle.from_bounds(14, 2, 18, 3),
        Rectangle.from_bounds(14, 7, 18, 8),
        Rectangle.from_bounds(14, 2, 15, 8),
        Rectangle.from_bounds(17, 2, 18, 8),
    )
    return Environment(bounds=(0, 0, 20, 10), start=(2, 5), goal=(16, 5), obstacles=walls)


@pytest.fixture
def wall_problem(wall_env: Environment) -> Problem:
    return Problem(wall_env)
