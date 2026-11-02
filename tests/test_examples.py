"""The examples are part of the documentation, so they must keep working."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mpplay.planners import get_planner, import_plugin_module, unregister_planner
from mpplay.runner import run_planner
from mpplay.scenarios import get_scenario

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def est():
    import_plugin_module(str(EXAMPLES / "est_planner.py"))
    yield get_planner("est")
    unregister_planner("est")


def test_est_plugin(est):
    info = est.info()
    assert info["label"] == "EST (plugin)"
    assert {p["name"] for p in info["params"]} == {"max_iterations", "radius"}
    for scenario in ("scattered", "bug_trap"):
        result = run_planner(get_scenario(scenario), "est", seed=1, raise_errors=True)
        assert result.success, result.message
        assert result.trace["num_steps"] == result.stats["iterations"]


@pytest.mark.slow
def test_compare_planners_script(tmp_path):
    pytest.importorskip("matplotlib")
    out = tmp_path / "cmp.png"
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLES / "compare_planners.py"),
            "--scenario",
            "slalom",
            "--trials",
            "1",
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "MPLBACKEND": "Agg"},
    )
    assert out.stat().st_size > 10_000
    assert "planner" in proc.stdout
