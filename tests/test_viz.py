from __future__ import annotations

import pytest

from mpplay.runner import run_planner
from mpplay.scenarios import get_scenario

plt = pytest.importorskip("matplotlib.pyplot")

from mpplay.viz import plot_environment, plot_result, save_result_plot  # noqa: E402


@pytest.mark.parametrize(
    "planner", ["astar", "rrt_connect", "prm", "potential_field", "informed_rrt_star"]
)
def test_plot_result(planner):
    env = get_scenario("slalom")
    params = {"max_iterations": 300} if planner == "informed_rrt_star" else None
    result = run_planner(env, planner, params, seed=0)
    fig, ax = plt.subplots()
    plot_result(env, result, ax=ax)
    assert ax.get_title()
    plt.close(fig)


def test_plot_environment_and_save(tmp_path):
    env = get_scenario("office")
    ax = plot_environment(env)
    assert len(ax.patches) >= len(env.obstacles)
    plt.close(ax.figure)
    out = tmp_path / "x.png"
    save_result_plot(env, run_planner(env, "astar").to_dict(), str(out))
    assert out.stat().st_size > 0
