from __future__ import annotations

import csv
import io

import pytest

from mpplay.benchmark import RunSpec, run_benchmark, summarize
from mpplay.scenarios import get_scenario


def test_run_spec_parse():
    spec = RunSpec.parse("astar:weight=2.5,connectivity=4,label=Fast A*,smooth=true")
    assert spec.planner == "astar"
    assert spec.params == {"weight": "2.5", "connectivity": "4"}
    assert spec.label == "Fast A*"
    assert spec.smoothing is True
    assert RunSpec.parse("rrt").display_label == "RRT"
    with pytest.raises(KeyError):
        RunSpec.parse("does_not_exist")
    with pytest.raises(ValueError, match="key=value"):
        RunSpec.parse("astar:weight")


def test_benchmark_rows_and_summary():
    envs = [get_scenario("bug_trap"), get_scenario("open_field")]
    specs = [RunSpec("astar"), RunSpec("rrt", label="RRT fast", params={"step_size": 5.0})]
    calls = []
    result = run_benchmark(
        envs, specs, trials=3, seed=10, progress=lambda d, t: calls.append((d, t))
    )
    assert len(result.rows) == 2 * 2 * 3
    assert calls[-1] == (12, 12)
    assert [r["seed"] for r in result.rows[:3]] == [10, 11, 12]
    summary = {(s["scenario"], s["run"]): s for s in result.summary}
    astar = summary[("Bug trap", "A*")]
    assert astar["success_rate"] == 1.0
    assert astar["path_length_std"] == 0.0  # deterministic planner
    assert summary[("Open field", "RRT fast")]["trials"] == 3


def test_summary_handles_failures():
    rows = [
        {"scenario": "s", "run": "r", "planner": "p", "success": False},
        {"scenario": "s", "run": "r", "planner": "p", "success": True, "path_length": 2.0},
    ]
    (entry,) = summarize(rows)
    assert entry["success_rate"] == 0.5
    assert entry["path_length_mean"] == 2.0
    assert entry["planning_time_ms_mean"] is None


def test_csv_export():
    result = run_benchmark([get_scenario("open_field")], [RunSpec("astar")], trials=2)
    rows = list(csv.DictReader(io.StringIO(result.rows_csv())))
    assert len(rows) == 2 and rows[0]["planner"] == "astar"
    summary = list(csv.DictReader(io.StringIO(result.summary_csv())))
    assert summary[0]["success_rate"] == "1.0"
