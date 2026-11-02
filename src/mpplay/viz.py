"""Static plots with matplotlib.

matplotlib is an optional dependency: ``pip install "motion-planning-playground[viz]"``.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import numpy as np

from .environment import Environment
from .geometry import Circle
from .trace import TraceState

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from .runner import PlanResult

START_COLOR = "#16a34a"
GOAL_COLOR = "#dc2626"
OBSTACLE_COLOR = "#475569"
PATH_COLOR = "#2563eb"


def _require_matplotlib() -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "Plotting needs matplotlib: pip install 'motion-planning-playground[viz]'"
        ) from exc
    return plt


def plot_environment(env: Environment, ax: Axes | None = None) -> Axes:
    """Draw bounds, obstacles, start and goal."""
    plt = _require_matplotlib()
    from matplotlib.patches import Circle as CirclePatch
    from matplotlib.patches import Patch
    from matplotlib.patches import Polygon as PolygonPatch
    from matplotlib.patches import Rectangle as RectPatch

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 10 * env.height / env.width))
    xmin, ymin, xmax, ymax = env.bounds
    ax.add_patch(
        RectPatch((xmin, ymin), env.width, env.height, fill=False, ec=OBSTACLE_COLOR, lw=2)
    )
    for obs in env.obstacles:
        patch: Patch
        if isinstance(obs, Circle):
            patch = CirclePatch(obs.center, obs.radius)
        else:
            patch = PolygonPatch(obs.vertices(), closed=True)
        patch.set_facecolor(OBSTACLE_COLOR)
        patch.set_edgecolor(OBSTACLE_COLOR)
        ax.add_patch(patch)
    r = max(env.robot_radius, 0.012 * env.diagonal)
    for p, color, label in ((env.start, START_COLOR, "start"), (env.goal, GOAL_COLOR, "goal")):
        ax.add_patch(CirclePatch(p, r, color=color, zorder=5, label=label))
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    return ax


def _decode_grid(data: dict[str, Any], key: str, dtype: Any) -> np.ndarray:
    nx, ny = data["shape"]
    raw = np.frombuffer(base64.b64decode(data[key]), dtype=dtype)
    return raw.reshape(ny, nx)


def plot_result(
    env: Environment,
    result: PlanResult | dict[str, Any],
    ax: Axes | None = None,
    exploration: bool = True,
    title: str | None = None,
) -> Axes:
    """Draw a planning result: explored cells/trees, overlays and the final path."""
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Ellipse as EllipsePatch

    data = result if isinstance(result, dict) else result.to_dict()
    ax = plot_environment(env, ax)
    extent = None
    for overlay in data.get("overlays") or []:
        if overlay.get("type") == "heatmap":
            img = _decode_grid(overlay, "values", np.uint8)
            ox, oy = overlay["origin"]
            nx, ny = overlay["shape"]
            res = overlay["resolution"]
            extent = (ox, ox + nx * res, oy, oy + ny * res)
            ax.imshow(img, origin="lower", extent=extent, cmap="magma_r", alpha=0.55, zorder=0)

    if exploration and data.get("trace"):
        state = TraceState.replay(data["trace"])
        grid = data.get("grid")
        if grid and (state.expanded or state.frontier):
            nx, ny = grid["shape"]
            res = grid["resolution"]
            ox, oy = grid["origin"]
            img = np.zeros((ny, nx, 4))
            for i, j in state.frontier:
                img[j, i] = (0.98, 0.75, 0.14, 0.45)
            for i, j in state.expanded:
                img[j, i] = (0.23, 0.51, 0.96, 0.35)
            ax.imshow(img, origin="lower", extent=(ox, ox + nx * res, oy, oy + ny * res), zorder=1)
        if state.edges:
            colors = {"tree2": "#f59e0b", "roadmap": "#94a3b8", "trajectory": "#a855f7"}
            segs = [((e[0], e[1]), (e[2], e[3])) for e in state.edges.values()]
            cols = [colors.get(e[4], "#60a5fa") for e in state.edges.values()]
            ax.add_collection(LineCollection(segs, colors=cols, linewidths=0.6, zorder=2))
        if state.nodes:
            pts = np.array([(n[0], n[1]) for n in state.nodes])
            ax.scatter(pts[:, 0], pts[:, 1], s=3, color="#64748b", zorder=2)
        for geom in state.overlays.values():
            if geom.get("type") == "ellipse":
                ax.add_patch(
                    EllipsePatch(
                        geom["center"],
                        2 * geom["rx"],
                        2 * geom["ry"],
                        angle=float(np.degrees(geom["angle"])),
                        fill=False,
                        ls="--",
                        lw=1.2,
                        ec=PATH_COLOR,
                        zorder=2,
                    )
                )

    path = data.get("path")
    if path:
        pts = np.asarray(path)
        ax.plot(pts[:, 0], pts[:, 1], color="white", lw=4.5, zorder=3, solid_capstyle="round")
        ax.plot(pts[:, 0], pts[:, 1], color=PATH_COLOR, lw=2.5, zorder=4, solid_capstyle="round")
    label = data.get("label", data.get("planner", ""))
    if title is None:
        metrics = data.get("metrics", {})
        if data.get("success"):
            title = (
                f"{label} - length {metrics.get('path_length', 0):.2f}, "
                f"{metrics.get('planning_time_ms', 0):.1f} ms"
            )
        else:
            title = f"{label} - {data.get('message') or 'failed'}"
    ax.set_title(title)
    return ax


def save_result_plot(env: Environment, result: PlanResult | dict[str, Any], path: str) -> None:
    plt = _require_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 10 * env.height / env.width))
    plot_result(env, result, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
