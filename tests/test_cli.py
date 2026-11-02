from __future__ import annotations

import json
import textwrap

import pytest

from mpplay.cli import main
from mpplay.environment import Environment
from mpplay.planners import unregister_planner


def test_planners_and_scenarios(capsys):
    assert main(["planners"]) == 0
    out = capsys.readouterr().out
    assert "astar" in out and "Sampling-based" in out
    assert main(["planners", "-v"]) == 0
    assert "--param weight=" in capsys.readouterr().out
    assert main(["scenarios", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["environment"]["bounds"]


def test_plan_writes_result_and_plot(tmp_path, capsys):
    out = tmp_path / "result.json"
    plot = tmp_path / "plot.png"
    code = main(
        [
            "plan",
            "-s",
            "bug_trap",
            "-p",
            "astar",
            "--param",
            "weight=2",
            "-o",
            str(out),
            "--plot",
            str(plot),
        ]
    )
    assert code == 0
    data = json.loads(out.read_text())
    assert data["result"]["success"] and data["result"]["trace"]
    assert Environment.from_dict(data["environment"]).name == "Bug trap"
    assert plot.stat().st_size > 10_000
    assert "path_length" in capsys.readouterr().out


def test_plan_failure_exit_code(capsys):
    assert main(["plan", "-s", "bug_trap", "-p", "potential_field"]) == 1
    assert "local minimum" in capsys.readouterr().out


def test_plan_bad_input(capsys):
    assert main(["plan", "-p", "nope"]) == 2
    assert main(["plan", "-p", "astar", "--param", "weight=0"]) == 2
    with pytest.raises(SystemExit):
        main(["plan", "-s", "atlantis"])


def test_benchmark_csv(tmp_path, capsys):
    rows = tmp_path / "rows.csv"
    summary = tmp_path / "summary.csv"
    code = main(
        [
            "benchmark",
            "-s",
            "open_field",
            "-p",
            "astar",
            "-p",
            "rrt:step_size=5,label=RRT big",
            "-n",
            "2",
            "-q",
            "--csv",
            str(rows),
            "--summary-csv",
            str(summary),
        ]
    )
    assert code == 0
    assert "RRT big" in capsys.readouterr().out
    assert len(rows.read_text().strip().splitlines()) == 1 + 4
    assert "success_rate" in summary.read_text()


def test_export_and_generate(tmp_path, capsys):
    path = tmp_path / "maze.json"
    assert main(["export", "maze", "-o", str(path)]) == 0
    assert Environment.load(path).name == "Maze"
    capsys.readouterr()
    assert main(["generate", "forest", "--param", "count=5", "--seed", "2"]) == 0
    env = Environment.from_json(capsys.readouterr().out)
    assert len(env.obstacles) == 5
    assert main(["generate", "nope"]) == 2


def test_plan_with_env_file(tmp_path, capsys):
    path = tmp_path / "env.json"
    main(["export", "slalom", "-o", str(path)])
    assert main(["plan", "-e", str(path), "-p", "rrt_connect", "--seed", "1"]) == 0


def test_plugin_file(tmp_path, capsys):
    plugin = tmp_path / "my_planner.py"
    plugin.write_text(
        textwrap.dedent(
            """
            from mpplay import Planner, PlanOutcome, register_planner

            @register_planner
            class Direct(Planner):
                name = "test_cli_direct"
                label = "Direct"
                summary = "Straight to the goal."

                def plan(self, problem, rng, rec):
                    return PlanOutcome([problem.start, problem.goal])
            """
        )
    )
    try:
        assert (
            main(["--plugin", str(plugin), "plan", "-s", "open_field", "-p", "test_cli_direct"])
            == 0
        )
        assert "success" in capsys.readouterr().out
    finally:
        unregister_planner("test_cli_direct")
