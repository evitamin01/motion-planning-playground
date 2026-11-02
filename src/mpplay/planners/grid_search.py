"""Graph search on the rasterized occupancy grid."""

from __future__ import annotations

import heapq
import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..environment import Problem
from ..geometry import Point
from ..grid import SQRT2, Cell, OccupancyGrid
from ..params import ParamsBase, param
from ..trace import Recorder
from .base import Planner, PlanningError, PlanOutcome, register_planner

GRAPH_SEARCH = "Graph search"

HEURISTICS = ["auto", "euclidean", "octile", "manhattan", "chebyshev", "zero"]


def _offsets(connectivity: str) -> list[tuple[int, int, float]]:
    """Neighbor offsets ``(di, dj, cost in cells)``."""
    straight = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0)]
    if connectivity == "4":
        return straight
    return [*straight, (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2)]


def heuristic_fn(name: str, goal: Cell, connectivity: str) -> Callable[[int, int], float]:
    """Heuristic in *cell* units for cell ``(i, j)``."""
    if name == "auto":
        name = "manhattan" if connectivity == "4" else "octile"
    gi, gj = goal
    if name == "euclidean":
        return lambda i, j: math.hypot(i - gi, j - gj)
    if name == "manhattan":
        return lambda i, j: abs(i - gi) + abs(j - gj)
    if name == "octile":

        def octile(i: int, j: int) -> float:
            dx, dy = abs(i - gi), abs(j - gj)
            return max(dx, dy) + (SQRT2 - 1.0) * min(dx, dy)

        return octile
    if name == "chebyshev":
        return lambda i, j: max(abs(i - gi), abs(j - gj))
    if name == "zero":
        return lambda i, j: 0.0
    raise ValueError(f"unknown heuristic {name!r}")


class GridPlanner(Planner):
    """Common plumbing for planners that search the occupancy grid."""

    uses_grid = True

    def setup(self, problem: Problem) -> None:
        problem.grid()

    @staticmethod
    def endpoints(problem: Problem, grid: OccupancyGrid) -> tuple[Cell, Cell]:
        start = grid.cell_of(problem.start)
        goal = grid.cell_of(problem.goal)
        for label, cell in (("start", start), ("goal", goal)):
            if cell is None or not grid.is_free(cell):
                raise PlanningError(
                    f"The {label} lies in an occupied grid cell. Grid cells are blocked "
                    "conservatively; try a finer resolution or move the "
                    f"{label} away from obstacles."
                )
        assert start is not None
        assert goal is not None
        return start, goal

    @staticmethod
    def cells_to_path(problem: Problem, grid: OccupancyGrid, cells: list[Cell]) -> list[Point]:
        """Turn a cell sequence into a world-space path from the exact start to the exact goal."""
        centers = [grid.center(i, j) for i, j in cells]
        if len(cells) == 1:
            return [problem.start, problem.goal]
        return [problem.start, *centers, problem.goal]


def _reconstruct(parent: dict[int, int], goal: int, ny: int) -> list[Cell]:
    cells = []
    k: int | None = goal
    while k is not None and k >= 0:
        cells.append(divmod(k, ny))
        k = parent.get(k)
    cells.reverse()
    return cells


# --------------------------------------------------------------------------- best-first search


@dataclass
class _SearchResult:
    cells: list[Cell] | None
    expansions: int
    generated: int


def best_first_search(
    grid: OccupancyGrid,
    start: Cell,
    goal: Cell,
    connectivity: str,
    priority: Callable[[float, float], float],
    heuristic: Callable[[int, int], float],
    rec: Recorder,
) -> _SearchResult:
    """Generic best-first search; ``priority(g, h)`` defines the algorithm (A*, Dijkstra, ...)."""
    nx, ny = grid.shape
    blocked = grid.blocked_bytes()
    offsets = _offsets(connectivity)
    s = start[0] * ny + start[1]
    t = goal[0] * ny + goal[1]
    g: dict[int, float] = {s: 0.0}
    parent: dict[int, int] = {s: -1}
    closed = bytearray(nx * ny)
    h0 = heuristic(*start)
    heap: list[tuple[float, float, int, int]] = [(priority(0.0, h0), h0, 0, s)]
    counter = 1
    expansions = 0
    rec.frontier(*start)
    while heap:
        _, _, _, k = heapq.heappop(heap)
        if closed[k]:
            continue
        closed[k] = 1
        expansions += 1
        i, j = divmod(k, ny)
        rec.step()
        rec.expand(i, j)
        if k == t:
            return _SearchResult(_reconstruct(parent, t, ny), expansions, counter)
        gk = g[k]
        for di, dj, cost in offsets:
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                continue
            nk = ni * ny + nj
            if blocked[nk] or closed[nk]:
                continue
            # No corner cutting: a diagonal move needs both adjacent straight cells free.
            if di and dj and (blocked[ni * ny + j] or blocked[i * ny + nj]):
                continue
            ng = gk + cost
            if ng < g.get(nk, math.inf):
                g[nk] = ng
                parent[nk] = k
                h = heuristic(ni, nj)
                heapq.heappush(heap, (priority(ng, h), h, counter, nk))
                counter += 1
                rec.frontier(ni, nj)
    return _SearchResult(None, expansions, counter)


@dataclass
class ConnectivityParams(ParamsBase):
    connectivity: str = param(
        "8",
        choices=["4", "8"],
        label="Connectivity",
        help="4: move horizontally/vertically only. 8: diagonal moves allowed (no corner cutting).",
    )


@dataclass
class AStarParams(ParamsBase):
    connectivity: str = param(
        "8",
        choices=["4", "8"],
        label="Connectivity",
        help="4: move horizontally/vertically only. 8: diagonal moves allowed (no corner cutting).",
    )
    heuristic: str = param(
        "auto",
        choices=HEURISTICS,
        label="Heuristic",
        help="Estimate of the remaining cost. 'auto' picks the tightest admissible one "
        "(Manhattan for 4-connectivity, octile for 8).",
    )
    weight: float = param(
        1.0,
        min=1.0,
        max=10.0,
        step=0.1,
        label="Heuristic weight",
        help="f = g + w*h. w > 1 gives Weighted A*: faster, at most w times longer than optimal.",
    )


@dataclass
class GreedyParams(ParamsBase):
    connectivity: str = param(
        "8",
        choices=["4", "8"],
        label="Connectivity",
        help="4: move horizontally/vertically only. 8: diagonal moves allowed (no corner cutting).",
    )
    heuristic: str = param(
        "euclidean",
        choices=HEURISTICS[1:],
        label="Heuristic",
        help="Estimate of the remaining cost.",
    )


class _BestFirstPlanner(GridPlanner):
    def _priority(self) -> Callable[[float, float], float]:
        raise NotImplementedError

    def _heuristic_name(self) -> str:
        return "zero"

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        grid = problem.grid()
        start, goal = self.endpoints(problem, grid)
        conn = self.params.connectivity
        result = best_first_search(
            grid,
            start,
            goal,
            conn,
            self._priority(),
            heuristic_fn(self._heuristic_name(), goal, conn),
            rec,
        )
        stats = {"expansions": result.expansions, "generated": result.generated}
        if result.cells is None:
            return PlanOutcome(None, "No path exists on the grid.", stats)
        stats["path_cells"] = len(result.cells)
        return PlanOutcome(self.cells_to_path(problem, grid, result.cells), "", stats)


@register_planner
class Dijkstra(_BestFirstPlanner):
    name = "dijkstra"
    label = "Dijkstra"
    family = GRAPH_SEARCH
    summary = "Uniform-cost search: expands cells in order of their distance from the start."
    description = """
Dijkstra's algorithm grows a frontier of cells outward from the start in order
of increasing path cost g(n). Every cell that is expanded has its final,
optimal cost, so the first time the goal is expanded the path is the shortest
path on the grid.

Because it uses no information about where the goal is, the explored region
looks like a growing "ripple" and it typically expands far more cells than A*.
It is A* with a zero heuristic.
"""
    properties = {
        "Complete": "Yes (resolution-complete)",
        "Optimal": "Yes, on the grid",
        "Heuristic": "None",
    }
    references = ["E. W. Dijkstra, 'A note on two problems in connexion with graphs', 1959."]
    Params = ConnectivityParams

    def _priority(self) -> Callable[[float, float], float]:
        return lambda g, h: g


@register_planner
class AStar(_BestFirstPlanner):
    name = "astar"
    label = "A*"
    family = GRAPH_SEARCH
    summary = "Best-first search guided by cost-so-far plus a heuristic estimate to the goal."
    description = """
A* expands the frontier cell with the lowest f(n) = g(n) + w*h(n), where g is
the cost from the start and h is a heuristic estimate of the cost to the goal.
With an admissible heuristic (one that never overestimates) and w = 1, the
returned path is optimal on the grid while far fewer cells are expanded than
with Dijkstra.

Increasing the weight w turns it into Weighted A*: the search becomes greedier
and faster, and the path is guaranteed to be at most w times longer than the
optimum. Try comparing w = 1 and w = 3 side by side.
"""
    properties = {
        "Complete": "Yes (resolution-complete)",
        "Optimal": "Yes with w = 1 and an admissible heuristic; else w-suboptimal",
        "Heuristic": "Configurable",
    }
    references = [
        "P. E. Hart, N. J. Nilsson, B. Raphael, 'A formal basis for the heuristic determination "
        "of minimum cost paths', IEEE Trans. SSC, 1968.",
        "I. Pohl, 'Heuristic search viewed as path finding in a graph', AI, 1970.",
    ]
    Params = AStarParams

    def _priority(self) -> Callable[[float, float], float]:
        w = self.params.weight
        return lambda g, h: g + w * h

    def _heuristic_name(self) -> str:
        return str(self.params.heuristic)


@register_planner
class GreedyBestFirst(_BestFirstPlanner):
    name = "greedy"
    label = "Greedy Best-First"
    family = GRAPH_SEARCH
    summary = "Always expands the cell that looks closest to the goal, ignoring the cost so far."
    description = """
Greedy best-first search orders the frontier by the heuristic h(n) alone. It
rushes towards the goal and often finds a path after very few expansions, but
it ignores how long the path already is, so the result can be far from optimal.

Obstacles that face the goal (such as the "bug trap") are its worst case: it
fills the dead end before it finds the way around it.
"""
    properties = {"Complete": "Yes (finite grid)", "Optimal": "No", "Heuristic": "Configurable"}
    references = ["J. Pearl, 'Heuristics', Addison-Wesley, 1984."]
    Params = GreedyParams

    def _priority(self) -> Callable[[float, float], float]:
        return lambda g, h: h

    def _heuristic_name(self) -> str:
        return str(self.params.heuristic)


@register_planner
class BreadthFirst(GridPlanner):
    name = "bfs"
    label = "Breadth-First Search"
    family = GRAPH_SEARCH
    summary = "Explores the grid layer by layer; finds the path with the fewest moves."
    description = """
Breadth-first search uses a first-in-first-out queue and explores all cells
reachable in k moves before any cell that needs k + 1 moves. It finds the path
with the fewest moves, which is the shortest path only when all moves cost the
same, so with 8-connectivity diagonal steps are treated like straight ones.

It is the simplest complete search algorithm and a useful baseline.
"""
    properties = {
        "Complete": "Yes (resolution-complete)",
        "Optimal": "Fewest moves (not shortest distance with diagonals)",
        "Heuristic": "None",
    }
    references = ["E. F. Moore, 'The shortest path through a maze', 1959."]
    Params = ConnectivityParams

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        grid = problem.grid()
        start, goal = self.endpoints(problem, grid)
        nx, ny = grid.shape
        blocked = grid.blocked_bytes()
        offsets = _offsets(self.params.connectivity)
        s = start[0] * ny + start[1]
        t = goal[0] * ny + goal[1]
        parent: dict[int, int] = {s: -1}
        queue = deque([s])
        rec.frontier(*start)
        expansions = 0
        while queue:
            k = queue.popleft()
            i, j = divmod(k, ny)
            expansions += 1
            rec.step()
            rec.expand(i, j)
            if k == t:
                cells = _reconstruct(parent, t, ny)
                stats = {
                    "expansions": expansions,
                    "generated": len(parent),
                    "path_cells": len(cells),
                }
                return PlanOutcome(self.cells_to_path(problem, grid, cells), "", stats)
            for di, dj, _ in offsets:
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                    continue
                nk = ni * ny + nj
                if blocked[nk] or nk in parent:
                    continue
                if di and dj and (blocked[ni * ny + j] or blocked[i * ny + nj]):
                    continue
                parent[nk] = k
                queue.append(nk)
                rec.frontier(ni, nj)
        stats = {"expansions": expansions, "generated": len(parent)}
        return PlanOutcome(None, "No path exists on the grid.", stats)


# --------------------------------------------------------------------------- Theta*


@dataclass
class ThetaStarParams(ParamsBase):
    lazy: bool = param(
        True,
        label="Lazy line-of-sight",
        help="Lazy Theta* checks line of sight once per expansion instead of once per "
        "neighbor: much faster, nearly identical paths.",
    )


@register_planner
class ThetaStar(GridPlanner):
    name = "theta_star"
    label = "Theta*"
    family = GRAPH_SEARCH
    summary = "Any-angle A*: a cell's parent may be any visible cell, giving short, smooth paths."
    description = """
Grid paths are restricted to 45 degree headings, which makes them longer and
jagged. Theta* is a variant of A* that lets the parent of a cell be any cell
with line of sight to it, not only a grid neighbor. When a neighbor s' of the
expanded cell s is visible from parent(s), it is connected straight to
parent(s), skipping s.

The resulting "any-angle" paths are much closer to the true shortest path in
the continuous plane. The lazy variant postpones the line-of-sight test until a
cell is expanded. The edges drawn during the search show each cell's parent.
"""
    properties = {
        "Complete": "Yes (resolution-complete)",
        "Optimal": "No, but usually near-optimal any-angle paths",
        "Heuristic": "Euclidean",
    }
    references = [
        "K. Daniel, A. Nash, S. Koenig, A. Felner, 'Theta*: Any-angle path planning on grids', "
        "JAIR, 2010.",
        "A. Nash, S. Koenig, C. Tovey, 'Lazy Theta*: Any-angle path planning and path length "
        "analysis in 3D', AAAI, 2010.",
    ]
    Params = ThetaStarParams

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        grid = problem.grid()
        start, goal = self.endpoints(problem, grid)
        nx, ny = grid.shape
        blocked = grid.blocked_bytes()
        offsets = _offsets("8")
        lazy = bool(self.params.lazy)
        gi, gj = goal
        g: dict[Cell, float] = {start: 0.0}
        parent: dict[Cell, Cell] = {start: start}
        closed: set[Cell] = set()
        heap: list[tuple[float, int, Cell]] = [(math.hypot(start[0] - gi, start[1] - gj), 0, start)]
        counter = 1
        expansions = 0
        los_checks = 0

        def dist(a: Cell, b: Cell) -> float:
            return math.hypot(a[0] - b[0], a[1] - b[1])

        def neighbors(c: Cell) -> list[Cell]:
            i, j = c
            out = []
            for di, dj, _ in offsets:
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= nx or nj >= ny or blocked[ni * ny + nj]:
                    continue
                if di and dj and (blocked[ni * ny + j] or blocked[i * ny + nj]):
                    continue
                out.append((ni, nj))
            return out

        rec.frontier(*start)
        while heap:
            _, _, s = heapq.heappop(heap)
            if s in closed:
                continue
            if lazy and s != start:
                los_checks += 1
                if not grid.line_of_sight(parent[s], s):
                    # Fall back to the best closed grid neighbor ("path 1").
                    best = min(
                        (n for n in neighbors(s) if n in closed),
                        key=lambda n: g[n] + dist(n, s),
                    )
                    parent[s] = best
                    g[s] = g[best] + dist(best, s)
            closed.add(s)
            expansions += 1
            rec.step()
            rec.expand(*s)
            if s != start:
                key = s[0] * ny + s[1]
                rec.edge(key, grid.center(*parent[s]), grid.center(*s), "tree")
            if s == goal:
                cells = [s]
                while cells[-1] != start:
                    cells.append(parent[cells[-1]])
                cells.reverse()
                stats = {
                    "expansions": expansions,
                    "generated": counter,
                    "line_of_sight_checks": los_checks,
                }
                return PlanOutcome(self.cells_to_path(problem, grid, cells), "", stats)
            ps = parent[s]
            for n in neighbors(s):
                if n in closed:
                    continue
                if lazy:
                    cand_parent = ps
                else:
                    los_checks += 1
                    cand_parent = ps if grid.line_of_sight(ps, n) else s
                cand = g[cand_parent] + dist(cand_parent, n)
                if cand < g.get(n, math.inf):
                    g[n] = cand
                    parent[n] = cand_parent
                    heapq.heappush(heap, (cand + math.hypot(n[0] - gi, n[1] - gj), counter, n))
                    counter += 1
                    rec.frontier(*n)
        stats = {"expansions": expansions, "generated": counter, "line_of_sight_checks": los_checks}
        return PlanOutcome(None, "No path exists on the grid.", stats)
