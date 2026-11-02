"""Repeated, untraced planner runs with aggregate statistics."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .environment import Environment, Problem
from .planners import get_planner
from .runner import run_planner

#: Metrics aggregated over successful trials.
SUMMARY_METRICS = [
    "path_length",
    "planning_time_ms",
    "turning_deg",
    "min_clearance",
    "waypoints",
    "collision_checks",
]


@dataclass
class RunSpec:
    """A planner configuration to benchmark."""

    planner: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    smoothing: bool = False

    @property
    def display_label(self) -> str:
        return self.label or get_planner(self.planner).label

    @classmethod
    def parse(cls, text: str) -> RunSpec:
        """Parse ``name`` or ``name:key=value,key=value`` (CLI syntax)."""
        name, _, rest = text.partition(":")
        params: dict[str, Any] = {}
        label = None
        smoothing = False
        for item in filter(None, (s.strip() for s in rest.split(","))):
            key, sep, value = item.partition("=")
            if not sep:
                raise ValueError(f"expected key=value in {text!r}, got {item!r}")
            key = key.strip()
            if key == "label":
                label = value
            elif key == "smooth":
                smoothing = value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                params[key] = value
        get_planner(name)  # validate early
        return cls(name.strip(), params, label, smoothing)


@dataclass
class BenchmarkResult:
    rows: list[dict[str, Any]]
    summary: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"rows": self.rows, "summary": self.summary}

    def rows_csv(self) -> str:
        return _to_csv(self.rows)

    def summary_csv(self) -> str:
        return _to_csv(self.summary)


def _to_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    keys: list[str] = []
    for row in rows:
        keys.extend(k for k in row if k not in keys)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def run_benchmark(
    environments: Iterable[Environment],
    specs: Sequence[RunSpec],
    trials: int = 10,
    seed: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> BenchmarkResult:
    """Run every spec ``trials`` times on every environment.

    Trial ``t`` uses seed ``seed + t`` for every planner, so results are
    reproducible. Rasterized grids are shared between all runs on the same
    environment and are excluded from planning time (see ``setup_time_ms``).
    """
    envs = list(environments)
    total = len(envs) * len(specs) * trials
    done = 0
    rows: list[dict[str, Any]] = []
    for env in envs:
        problem = Problem(env)
        for spec in specs:
            for t in range(trials):
                result = run_planner(
                    problem,
                    spec.planner,
                    spec.params,
                    seed=seed + t,
                    trace=False,
                    smoothing=spec.smoothing,
                )
                row: dict[str, Any] = {
                    "scenario": env.name,
                    "run": spec.display_label,
                    "planner": spec.planner,
                    "trial": t,
                    "seed": seed + t,
                    "success": result.success,
                }
                row.update(result.metrics)
                row.update({f"stat_{k}": v for k, v in result.stats.items()})
                if not result.success:
                    row["message"] = result.message
                rows.append(row)
                done += 1
                if progress is not None:
                    progress(done, total)
    return BenchmarkResult(rows, summarize(rows))


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate rows per (scenario, run): success rate and mean/std/median of metrics."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["scenario"], row["run"]), []).append(row)
    out = []
    for (scenario, run), items in groups.items():
        ok = [r for r in items if r["success"]]
        entry: dict[str, Any] = {
            "scenario": scenario,
            "run": run,
            "planner": items[0]["planner"],
            "trials": len(items),
            "successes": len(ok),
            "success_rate": round(len(ok) / len(items), 4),
        }
        for key in SUMMARY_METRICS:
            values = np.array([r[key] for r in ok if r.get(key) is not None], dtype=float)
            if len(values):
                entry[f"{key}_mean"] = _round(values.mean())
                entry[f"{key}_std"] = _round(values.std(ddof=1)) if len(values) > 1 else 0.0
                entry[f"{key}_median"] = _round(float(np.median(values)))
                entry[f"{key}_min"] = _round(values.min())
                entry[f"{key}_max"] = _round(values.max())
            else:
                for stat in ("mean", "std", "median", "min", "max"):
                    entry[f"{key}_{stat}"] = None
        out.append(entry)
    return out


def _round(v: float) -> float:
    return round(float(v), 4) if math.isfinite(v) else float("nan")
