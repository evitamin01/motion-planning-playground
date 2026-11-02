"""Compare planners from Python and save a figure (requires matplotlib).

    python examples/compare_planners.py --scenario maze --output comparison.png

The same building blocks power the web UI: scenarios, `run_planner`,
`run_benchmark` and the matplotlib helpers in `mpplay.viz`.
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt

from mpplay import RunSpec, get_scenario, run_benchmark, run_planner
from mpplay.viz import plot_result

PLANNERS = ["astar", "theta_star", "rrt_connect", "rrt_star", "prm", "potential_field"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="scattered")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", default="comparison.png")
    args = parser.parse_args()

    env = get_scenario(args.scenario)

    # 1. One traced run per planner, drawn side by side.
    fig, axes = plt.subplots(2, 3, figsize=(15, 6.6))
    for ax, name in zip(axes.flat, PLANNERS, strict=True):
        result = run_planner(env, name, seed=args.seed)
        plot_result(env, result, ax=ax)
    fig.suptitle(f"{env.name}: {env.description}", fontsize=10)
    fig.tight_layout()
    fig.savefig(args.output, dpi=130)
    print(f"wrote {args.output}")

    # 2. A small statistical benchmark (untraced, several seeds).
    bench = run_benchmark([env], [RunSpec(n) for n in PLANNERS], trials=args.trials, seed=args.seed)
    print(f"\n{'planner':18s} {'success':>8s} {'length':>16s} {'time [ms]':>16s}")
    for s in bench.summary:
        length = "-" if s["path_length_mean"] is None else f"{s['path_length_mean']:.1f}"
        time = "-" if s["planning_time_ms_mean"] is None else f"{s['planning_time_ms_mean']:.1f}"
        print(f"{s['run']:18s} {s['success_rate']:8.0%} {length:>16s} {time:>16s}")


if __name__ == "__main__":
    main()
