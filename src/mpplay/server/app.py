"""FastAPI application serving the JSON API and the web UI.

Endpoints (all JSON):

* ``GET  /api/info``        - version and limits
* ``GET  /api/planners``    - registered planners with parameter schemas
* ``GET  /api/scenarios``   - built-in scenarios
* ``GET  /api/generators``  - procedural environment generators
* ``POST /api/generate``    - generate an environment
* ``POST /api/plan``        - run one planner (with trace)
* ``POST /api/benchmark``   - repeated untraced runs with statistics
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from importlib.resources import files
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..benchmark import RunSpec, run_benchmark
from ..environment import Environment, Problem
from ..metrics import METRICS
from ..planners import available_planners, get_planner
from ..runner import run_planner
from ..scenarios import GENERATORS, SCENARIOS

MAX_BENCHMARK_RUNS = 50_000
MAX_SPECS = 12
MAX_ENVIRONMENTS = 20

# Planners are CPU-bound Python code: running several at once in threads only makes
# them compete for the GIL and distorts the measured planning times. Requests are
# therefore executed one at a time, which keeps timings comparable.
_PLANNING_LOCK = threading.Lock()


class PlanRequest(BaseModel):
    environment: dict[str, Any]
    planner: str
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0
    smoothing: bool = False
    trace: bool = True


class GenerateRequest(BaseModel):
    generator: str
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0


class RunSpecModel(BaseModel):
    planner: str
    params: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None
    smoothing: bool = False


class BenchmarkRequest(BaseModel):
    environments: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_ENVIRONMENTS)
    runs: list[RunSpecModel] = Field(min_length=1, max_length=MAX_SPECS)
    trials: int = Field(10, ge=1, le=500)
    seed: int = 0


class _ProblemCache:
    """Small LRU cache so repeated runs on one environment share rasterized grids."""

    def __init__(self, size: int = 16) -> None:
        self.size = size
        self._items: OrderedDict[str, Problem] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, env: Environment) -> Problem:
        key = json.dumps(env.to_dict(), sort_keys=True)
        with self._lock:
            problem = self._items.get(key)
            if problem is None:
                problem = Problem(env)
                self._items[key] = problem
                if len(self._items) > self.size:
                    self._items.popitem(last=False)
            else:
                self._items.move_to_end(key)
            return problem


def _parse_environment(data: dict[str, Any]) -> Environment:
    try:
        return Environment.from_dict(data)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid environment: {exc}") from exc


def static_dir() -> Path:
    return Path(str(files("mpplay") / "web"))


class _RevalidatingStaticFiles(StaticFiles):
    """Static files that browsers must revalidate (cheap 304s), so upgrades are never stale."""

    async def get_response(self, path: str, scope: Any) -> Any:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(serve_static: bool = True) -> FastAPI:
    """Create the application.

    Args:
        serve_static: Also serve the bundled web UI at ``/``.
    """
    app = FastAPI(
        title="Motion Planning Playground",
        version=__version__,
        description="Explore, visualize and compare 2D motion planning algorithms.",
    )
    cache = _ProblemCache()

    @app.get("/api/info")
    def info() -> dict[str, Any]:
        return {
            "name": "Motion Planning Playground",
            "version": __version__,
            "metrics": [
                {"key": k, "label": label, "unit": unit, "lower_is_better": lower}
                for k, label, unit, lower in METRICS
            ],
            "limits": {
                "benchmark_runs": MAX_BENCHMARK_RUNS,
                "benchmark_specs": MAX_SPECS,
                "benchmark_environments": MAX_ENVIRONMENTS,
            },
        }

    @app.get("/api/planners")
    def planners() -> list[dict[str, Any]]:
        return [cls.info() for cls in available_planners()]

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [s.info() for s in SCENARIOS.values()]

    @app.get("/api/generators")
    def generators() -> list[dict[str, Any]]:
        return [g.info() for g in GENERATORS.values()]

    @app.post("/api/generate")
    def generate(req: GenerateRequest) -> dict[str, Any]:
        gen = GENERATORS.get(req.generator)
        if gen is None:
            raise HTTPException(status_code=404, detail=f"Unknown generator {req.generator!r}")
        try:
            return gen.generate(req.params, req.seed).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/plan")
    def plan(req: PlanRequest) -> dict[str, Any]:
        env = _parse_environment(req.environment)
        try:
            get_planner(req.planner)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        try:
            with _PLANNING_LOCK:
                result = run_planner(
                    cache.get(env),
                    req.planner,
                    req.params,
                    seed=req.seed,
                    trace=req.trace,
                    smoothing=req.smoothing,
                )
        except ValueError as exc:  # invalid parameters, grid too large, ...
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.to_dict()

    @app.post("/api/benchmark")
    def benchmark(req: BenchmarkRequest) -> dict[str, Any]:
        envs = [_parse_environment(e) for e in req.environments]
        total = len(envs) * len(req.runs) * req.trials
        if total > MAX_BENCHMARK_RUNS:
            raise HTTPException(
                status_code=422,
                detail=f"Benchmark too large ({total} runs, limit {MAX_BENCHMARK_RUNS}).",
            )
        try:
            specs = [RunSpec(r.planner, r.params, r.label, r.smoothing) for r in req.runs]
            for spec in specs:
                get_planner(spec.planner).Params.from_dict(spec.params)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with _PLANNING_LOCK:
            return run_benchmark(envs, specs, trials=req.trials, seed=req.seed).to_dict()

    if serve_static:
        # Mounted last so that the API routes above take precedence.
        app.mount("/", _RevalidatingStaticFiles(directory=static_dir(), html=True), name="web")

    return app
