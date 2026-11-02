from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mpplay import __version__
from mpplay.scenarios import get_scenario
from mpplay.server import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def env_dict() -> dict:
    return get_scenario("bug_trap").to_dict()


def test_info(client):
    data = client.get("/api/info").json()
    assert data["version"] == __version__
    assert any(m["key"] == "path_length" for m in data["metrics"])


def test_planners(client):
    planners = client.get("/api/planners").json()
    names = [p["name"] for p in planners]
    assert "astar" in names and "rrt_star" in names
    astar = next(p for p in planners if p["name"] == "astar")
    assert {s["name"] for s in astar["params"]} == {"connectivity", "heuristic", "weight"}


def test_scenarios_and_generators(client):
    scenarios = client.get("/api/scenarios").json()
    assert {"name", "label", "description", "environment"} <= set(scenarios[0])
    gens = client.get("/api/generators").json()
    assert {g["name"] for g in gens} == {"maze", "forest", "shapes"}
    env = client.post(
        "/api/generate", json={"generator": "maze", "params": {"cols": 4}, "seed": 3}
    ).json()
    assert env["bounds"] == [0.0, 0.0, 100.0, 60.0]
    assert client.post("/api/generate", json={"generator": "nope"}).status_code == 404
    assert (
        client.post("/api/generate", json={"generator": "maze", "params": {"cols": 0}}).status_code
        == 422
    )


def test_plan(client, env_dict):
    res = client.post(
        "/api/plan", json={"environment": env_dict, "planner": "astar", "params": {"weight": 2}}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["params"]["weight"] == 2.0
    assert data["trace"]["num_steps"] == data["stats"]["expansions"]
    assert data["grid"]["shape"] == [100, 60]


def test_plan_without_trace(client, env_dict):
    data = client.post(
        "/api/plan",
        json={
            "environment": env_dict,
            "planner": "rrt",
            "seed": 2,
            "trace": False,
            "smoothing": True,
        },
    ).json()
    assert data["success"] and data["trace"] is None and data["raw_path"]


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"planner": "nope"}, 404),
        ({"planner": "astar", "params": {"weight": 0}}, 422),
        ({"planner": "astar", "params": {"bogus": 1}}, 422),
        ({"planner": "astar", "environment": {"bounds": [0, 0, 1]}}, 422),
    ],
)
def test_plan_errors(client, env_dict, body, status):
    payload = {"environment": env_dict, **body}
    res = client.post("/api/plan", json=payload)
    assert res.status_code == status
    assert isinstance(res.json()["detail"], str)


def test_plan_reports_oversized_grid(client):
    env = {"bounds": [0, 0, 10, 10], "start": [1, 1], "goal": [2, 2], "resolution": 0.001}
    data = client.post("/api/plan", json={"environment": env, "planner": "astar"}).json()
    assert data["success"] is False
    assert "exceeds the limit" in data["message"]


def test_benchmark(client, env_dict):
    body = {
        "environments": [env_dict],
        "runs": [
            {"planner": "astar"},
            {"planner": "rrt", "label": "RRT!", "params": {"step_size": 4}},
        ],
        "trials": 2,
        "seed": 5,
    }
    data = client.post("/api/benchmark", json=body).json()
    assert len(data["rows"]) == 4
    assert {s["run"] for s in data["summary"]} == {"A*", "RRT!"}


def test_benchmark_validation(client, env_dict):
    bad = {
        "environments": [env_dict],
        "runs": [{"planner": "astar", "params": {"weight": -1}}],
        "trials": 1,
    }
    assert client.post("/api/benchmark", json=bad).status_code == 422
    too_many = {"environments": [env_dict], "runs": [{"planner": "astar"}], "trials": 10_000}
    assert client.post("/api/benchmark", json=too_many).status_code == 422


def test_static_ui_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Motion Planning Playground" in res.text
    assert res.headers["cache-control"] == "no-cache"
    assert client.get("/js/main.js").status_code == 200
    assert client.get("/css/app.css").status_code == 200
