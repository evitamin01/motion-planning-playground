"""Sampling-based planners in continuous space (RRT family and PRM)."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..collision import CollisionChecker
from ..environment import Problem
from ..geometry import FloatArray, Point
from ..params import ParamsBase, param
from ..trace import Recorder
from .base import Planner, PlanOutcome, register_planner

SAMPLING = "Sampling-based"


class Tree:
    """A growing tree with vectorized nearest-neighbor queries."""

    def __init__(self, root: Point, capacity: int = 1024) -> None:
        self.points = np.empty((capacity, 2))
        self.parent = np.full(capacity, -1, dtype=np.intp)
        self.cost = np.zeros(capacity)
        self.size = 0
        self.add(root, -1, 0.0)

    def add(self, p: Point | FloatArray, parent: int, cost: float) -> int:
        if self.size == len(self.points):
            grow = len(self.points)
            self.points = np.concatenate([self.points, np.empty((grow, 2))])
            self.parent = np.concatenate([self.parent, np.full(grow, -1, dtype=np.intp)])
            self.cost = np.concatenate([self.cost, np.zeros(grow)])
        k = self.size
        self.points[k] = p
        self.parent[k] = parent
        self.cost[k] = cost
        self.size += 1
        return k

    def distances(self, p: FloatArray) -> FloatArray:
        return np.asarray(np.linalg.norm(self.points[: self.size] - p, axis=1))

    def nearest(self, p: FloatArray) -> int:
        return int(np.argmin(self.distances(p)))

    def k_nearest(self, p: FloatArray, k: int) -> NDArray[np.intp]:
        d = self.distances(p)
        if k >= self.size:
            return np.argsort(d)
        idx = np.argpartition(d, k)[:k]
        return idx[np.argsort(d[idx])]

    def path_to(self, k: int) -> list[Point]:
        out = []
        while k >= 0:
            out.append((float(self.points[k, 0]), float(self.points[k, 1])))
            k = int(self.parent[k])
        out.reverse()
        return out


def steer(a: FloatArray, b: FloatArray, step: float) -> FloatArray:
    """Move from ``a`` towards ``b`` by at most ``step``."""
    d = b - a
    n = float(np.hypot(d[0], d[1]))
    if n <= step:
        return b.copy()
    return np.asarray(a + d * (step / n))


class _Sampler:
    """Uniform samples over the region the robot center may occupy."""

    def __init__(self, checker: CollisionChecker, rng: np.random.Generator) -> None:
        r = checker.robot_radius
        xmin, ymin, xmax, ymax = checker.bounds
        self.lo = np.array([xmin + r, ymin + r])
        self.hi = np.array([xmax - r, ymax - r])
        self.rng = rng

    def uniform(self) -> FloatArray:
        return np.asarray(self.rng.uniform(self.lo, self.hi))

    def uniform_batch(self, n: int) -> FloatArray:
        return np.asarray(self.rng.uniform(self.lo, self.hi, size=(n, 2)))

    def inside(self, p: FloatArray) -> bool:
        return bool(np.all(p >= self.lo) and np.all(p <= self.hi))


@dataclass
class RRTParams(ParamsBase):
    max_iterations: int = param(
        5000, min=10, max=100_000, step=100, label="Max iterations", help="Sampling budget."
    )
    step_size: float = param(
        3.0,
        min=0.05,
        max=100.0,
        step=0.1,
        label="Step size",
        help="Maximum length of a new tree edge (world units).",
    )
    goal_bias: float = param(
        0.05,
        min=0.0,
        max=1.0,
        step=0.01,
        label="Goal bias",
        help="Probability of sampling the goal instead of a random point.",
    )


def _goal_array(problem: Problem) -> FloatArray:
    return np.asarray(problem.goal, dtype=float)


@register_planner
class RRT(Planner):
    name = "rrt"
    label = "RRT"
    family = SAMPLING
    summary = "Rapidly-exploring Random Tree: grows a tree towards random samples."
    description = """
RRT grows a tree rooted at the start. In every iteration it draws a random
sample (or, with a small probability, the goal), finds the nearest tree node
and extends it by one step towards the sample. If that short edge is
collision-free the new node is added. The search stops once a node can be
connected to the goal.

Because nodes with large empty regions around them (large Voronoi cells) are
most likely to be the nearest node to a random sample, the tree is pulled
rapidly into unexplored space. RRT finds feasible paths quickly in
high-dimensional spaces but the paths are jagged and not optimal.
"""
    properties = {
        "Complete": "Probabilistically complete",
        "Optimal": "No (converges to a suboptimal path)",
        "Space": "Continuous",
    }
    references = [
        "S. M. LaValle, 'Rapidly-exploring random trees: A new tool for path planning', "
        "TR 98-11, Iowa State University, 1998.",
    ]
    stochastic = True
    Params = RRTParams

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker
        sampler = _Sampler(checker, rng)
        goal = _goal_array(problem)
        tree = Tree(problem.start)
        start = tree.points[0]
        if np.linalg.norm(goal - start) <= p.step_size and checker.segment_free(start, goal):
            return PlanOutcome([problem.start, problem.goal], "", {"iterations": 0, "tree_size": 1})
        for it in range(1, p.max_iterations + 1):
            rec.step()
            q_rand = goal if rng.random() < p.goal_bias else sampler.uniform()
            rec.sample(q_rand)
            n = tree.nearest(q_rand)
            q_near = tree.points[n]
            q_new = steer(q_near, q_rand, p.step_size)
            if not checker.segment_free(q_near, q_new):
                continue
            k = tree.add(q_new, n, 0.0)
            rec.edge(k, q_near, q_new)
            if np.linalg.norm(goal - q_new) <= p.step_size and checker.segment_free(q_new, goal):
                g = tree.add(goal, k, 0.0) if not np.array_equal(q_new, goal) else k
                if g != k:
                    rec.edge(g, q_new, goal)
                return PlanOutcome(tree.path_to(g), "", {"iterations": it, "tree_size": tree.size})
        return PlanOutcome(
            None,
            f"No path found within {p.max_iterations} iterations.",
            {"iterations": p.max_iterations, "tree_size": tree.size},
        )


@register_planner
class RRTConnect(Planner):
    name = "rrt_connect"
    label = "RRT-Connect"
    family = SAMPLING
    summary = "Bidirectional RRT: grows trees from start and goal and greedily connects them."
    description = """
RRT-Connect grows two trees, one from the start and one from the goal. Each
iteration extends one tree by a step towards a random sample; the other tree
then greedily "connects": it keeps stepping towards the new node until it
either reaches it or hits an obstacle. Afterwards the roles of the trees are
swapped.

The greedy connect heuristic makes it one of the fastest single-query
planners for finding a first feasible path, but - like RRT - the path is not
optimized.
"""
    properties = {
        "Complete": "Probabilistically complete",
        "Optimal": "No",
        "Space": "Continuous",
    }
    references = [
        "J. J. Kuffner, S. M. LaValle, 'RRT-Connect: An efficient approach to single-query path "
        "planning', ICRA, 2000.",
    ]
    stochastic = True

    @dataclass
    class Params(ParamsBase):
        max_iterations: int = param(
            5000, min=10, max=100_000, step=100, label="Max iterations", help="Sampling budget."
        )
        step_size: float = param(
            3.0,
            min=0.05,
            max=100.0,
            step=0.1,
            label="Step size",
            help="Maximum length of a new tree edge (world units).",
        )

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker
        sampler = _Sampler(checker, rng)
        trees = [Tree(problem.start), Tree(problem.goal)]
        layers = ["tree", "tree2"]

        def extend(t: int, target: FloatArray) -> tuple[str, int]:
            tree = trees[t]
            n = tree.nearest(target)
            q_near = tree.points[n]
            q_new = steer(q_near, target, p.step_size)
            if not checker.segment_free(q_near, q_new):
                return "trapped", n
            k = tree.add(q_new, n, 0.0)
            rec.edge(2 * k + t, q_near, q_new, layers[t])
            return ("reached" if np.array_equal(q_new, target) else "advanced"), k

        a = 0
        for it in range(1, p.max_iterations + 1):
            rec.step()
            q_rand = sampler.uniform()
            rec.sample(q_rand)
            status, k = extend(a, q_rand)
            if status != "trapped":
                target = trees[a].points[k].copy()
                b = 1 - a
                while True:
                    status_b, kb = extend(b, target)
                    if status_b != "advanced":
                        break
                if status_b == "reached":
                    path_a = trees[a].path_to(k)
                    path_b = trees[b].path_to(kb)
                    # path_b ends at the shared node; drop the duplicate and reverse.
                    path_b = path_b[:-1][::-1]
                    path = path_a + path_b
                    if a == 1:
                        path.reverse()
                    stats = {
                        "iterations": it,
                        "tree_size": trees[0].size + trees[1].size,
                        "start_tree_size": trees[0].size,
                        "goal_tree_size": trees[1].size,
                    }
                    return PlanOutcome(path, "", stats)
            a = 1 - a
        return PlanOutcome(
            None,
            f"No path found within {p.max_iterations} iterations.",
            {"iterations": p.max_iterations, "tree_size": trees[0].size + trees[1].size},
        )


# --------------------------------------------------------------------------- RRT*


@dataclass
class RRTStarParams(ParamsBase):
    max_iterations: int = param(
        3000,
        min=10,
        max=50_000,
        step=100,
        label="Max iterations",
        help="Sampling budget. RRT* keeps improving the path until it is used up.",
    )
    step_size: float = param(
        3.0,
        min=0.05,
        max=100.0,
        step=0.1,
        label="Step size",
        help="Maximum distance between a new node and its nearest neighbor.",
    )
    goal_bias: float = param(
        0.05,
        min=0.0,
        max=1.0,
        step=0.01,
        label="Goal bias",
        help="Probability of sampling the goal instead of a random point.",
    )
    neighbor_factor: float = param(
        1.0,
        min=0.1,
        max=5.0,
        step=0.1,
        label="Neighbor factor",
        help="Scales the number of neighbors k = factor * e * (1 + 1/d) * log(n) "
        "considered for choosing a parent and rewiring.",
    )


@register_planner
class RRTStar(Planner):
    name = "rrt_star"
    label = "RRT*"
    family = SAMPLING
    summary = "Asymptotically optimal RRT: chooses the best parent and rewires neighbors."
    description = """
RRT* extends RRT with two optimizations. When a new node is added, it is
connected to the neighbor that gives it the lowest cost-from-start (choose
parent) rather than to the nearest node. Then each nearby node is re-attached
through the new node if that makes its path shorter (rewire).

The tree keeps improving as more samples arrive, and the solution converges
to the optimal path as the number of samples grows. Watch the best-cost curve
in the Charts tab: it drops quickly at first and then refines slowly. This
implementation uses the k-nearest variant (k grows logarithmically with the
tree size).
"""
    properties = {
        "Complete": "Probabilistically complete",
        "Optimal": "Asymptotically optimal",
        "Space": "Continuous",
    }
    references = [
        "S. Karaman, E. Frazzoli, 'Sampling-based algorithms for optimal motion planning', "
        "IJRR, 2011.",
    ]
    stochastic = True
    Params = RRTStarParams

    #: Whether to restrict sampling to the informed ellipse once a solution exists.
    informed = False

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker
        sampler = _Sampler(checker, rng)
        goal = _goal_array(problem)
        start = np.asarray(problem.start, dtype=float)
        tree = Tree(problem.start, capacity=p.max_iterations + 2)
        children: list[set[int]] = [set()]
        k_rrg = p.neighbor_factor * math.e * 1.5  # e * (1 + 1/d) for d = 2
        c_min = float(np.linalg.norm(goal - start))
        center = (start + goal) / 2
        angle = math.atan2(goal[1] - start[1], goal[0] - start[0])
        rot = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])

        goal_parents: list[int] = []  # nodes with a collision-free edge to the goal
        best_cost = math.inf
        best_parent = -1
        series: list[list[float]] = []
        first_solution = None
        rewires = 0

        def informed_sample() -> FloatArray:
            a = best_cost / 2
            b = math.sqrt(max(best_cost**2 - c_min**2, 0.0)) / 2
            for _ in range(100):
                # Uniform point in the unit disc, stretched to the ellipse.
                r = math.sqrt(rng.random())
                th = rng.uniform(0, 2 * math.pi)
                q = rot @ np.array([a * r * math.cos(th), b * r * math.sin(th)]) + center
                if sampler.inside(q):
                    return np.asarray(q)
            return sampler.uniform()

        def propagate(root: int, delta: float) -> None:
            stack = list(children[root])
            while stack:
                c = stack.pop()
                tree.cost[c] -= delta
                stack.extend(children[c])

        for it in range(1, p.max_iterations + 1):
            rec.step()
            if rng.random() < p.goal_bias:
                q_rand = goal
            elif self.informed and best_cost < math.inf:
                q_rand = informed_sample()
            else:
                q_rand = sampler.uniform()
            rec.sample(q_rand)
            nearest = tree.nearest(q_rand)
            q_new = steer(tree.points[nearest], q_rand, p.step_size)
            if not checker.segment_free(tree.points[nearest], q_new):
                continue

            k = max(1, math.ceil(k_rrg * math.log(tree.size + 1)))
            near = tree.k_nearest(q_new, k)
            if nearest not in near:
                near = np.append(near, nearest)
            d_near = np.linalg.norm(tree.points[near] - q_new, axis=1)
            free = checker.segments_free(tree.points[near], np.broadcast_to(q_new, (len(near), 2)))
            via = np.where(free, tree.cost[near] + d_near, np.inf)
            best = int(np.argmin(via))
            parent = int(near[best])
            new = tree.add(q_new, parent, float(via[best]))
            children.append(set())
            children[parent].add(new)
            rec.edge(new, tree.points[parent], q_new)

            # Rewire neighbors through the new node where that is cheaper.
            new_cost = tree.cost[new]
            for idx, n in enumerate(near):
                n = int(n)
                if not free[idx] or n == parent:
                    continue
                cand = new_cost + d_near[idx]
                if cand + 1e-12 < tree.cost[n]:
                    old_parent = int(tree.parent[n])
                    children[old_parent].discard(n)
                    children[new].add(n)
                    tree.parent[n] = new
                    delta = tree.cost[n] - cand
                    tree.cost[n] = cand
                    propagate(n, delta)
                    rewires += 1
                    rec.edge(n, q_new, tree.points[n])

            if np.linalg.norm(goal - q_new) <= p.step_size and checker.segment_free(q_new, goal):
                goal_parents.append(new)

            if goal_parents:
                gp = np.asarray(goal_parents)
                totals = tree.cost[gp] + np.linalg.norm(tree.points[gp] - goal, axis=1)
                i_best = int(np.argmin(totals))
                if totals[i_best] + 1e-9 < best_cost:
                    best_cost = float(totals[i_best])
                    best_parent = int(gp[i_best])
                    if first_solution is None:
                        first_solution = it
                    series.append([it, round(best_cost, 4)])
                    rec.path([*tree.path_to(best_parent), problem.goal])
                    if self.informed:
                        b_axis = math.sqrt(max(best_cost**2 - c_min**2, 0.0)) / 2
                        rec.overlay(
                            "informed_set",
                            {
                                "type": "ellipse",
                                "center": [round(float(center[0]), 4), round(float(center[1]), 4)],
                                "rx": round(best_cost / 2, 4),
                                "ry": round(b_axis, 4),
                                "angle": round(angle, 6),
                            },
                        )

        stats: dict[str, float | int] = {
            "iterations": p.max_iterations,
            "tree_size": tree.size,
            "rewires": rewires,
        }
        if first_solution is None:
            return PlanOutcome(None, f"No path found within {p.max_iterations} iterations.", stats)
        stats["first_solution_iteration"] = first_solution
        stats["first_solution_cost"] = series[0][1]
        if series[-1][0] != p.max_iterations:
            series.append([p.max_iterations, series[-1][1]])
        path = [*tree.path_to(best_parent), problem.goal]
        return PlanOutcome(path, "", stats, series={"best_cost": series})


@register_planner
class InformedRRTStar(RRTStar):
    name = "informed_rrt_star"
    label = "Informed RRT*"
    family = SAMPLING
    summary = "RRT* that, once a solution exists, only samples where a better path is possible."
    description = """
After RRT* finds a first solution of cost c_best, only states inside an ellipse
can still lie on a better path: the set of points x with
|x - start| + |goal - x| < c_best, an ellipse whose foci are the start and the
goal. Informed RRT* samples uniformly from this ellipse instead of the whole
map.

Every improvement shrinks the ellipse (drawn on the canvas), which focuses the
search and makes convergence much faster than plain RRT*, especially in large,
open maps.
"""
    properties = {
        "Complete": "Probabilistically complete",
        "Optimal": "Asymptotically optimal",
        "Space": "Continuous",
    }
    references = [
        "J. D. Gammell, S. S. Srinivasa, T. D. Barfoot, 'Informed RRT*: Optimal sampling-based "
        "path planning focused via direct sampling of an admissible ellipsoidal heuristic', "
        "IROS, 2014.",
    ]
    informed = True


# --------------------------------------------------------------------------- PRM


@register_planner
class PRM(Planner):
    name = "prm"
    label = "PRM"
    family = SAMPLING
    summary = "Probabilistic Roadmap: samples free space, links neighbors, then searches the graph."
    description = """
The Probabilistic Roadmap method works in two phases. In the construction
phase it scatters random collision-free samples over the map and connects
each one to its k nearest neighbors whenever the straight edge between them is
collision-free. The result is a graph (roadmap) that captures the
connectivity of the free space.

In the query phase the start and goal are connected to the roadmap and A* finds
the shortest route through it. Because the roadmap can be reused for many
queries, PRM is a multi-query planner. Narrow passages are hard for it: few
samples land inside them.
"""
    properties = {
        "Complete": "Probabilistically complete",
        "Optimal": "No (asymptotically optimal for PRM* connection rules)",
        "Space": "Continuous",
    }
    references = [
        "L. E. Kavraki, P. Svestka, J.-C. Latombe, M. H. Overmars, 'Probabilistic roadmaps for "
        "path planning in high-dimensional configuration spaces', IEEE T-RA, 1996.",
    ]
    stochastic = True

    @dataclass
    class Params(ParamsBase):
        num_samples: int = param(
            1000, min=10, max=10_000, step=50, label="Samples", help="Number of roadmap vertices."
        )
        k_neighbors: int = param(
            12,
            min=1,
            max=50,
            step=1,
            label="Neighbors (k)",
            help="Each vertex tries to connect to this many nearest vertices.",
        )

    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker
        sampler = _Sampler(checker, rng)

        # Construction phase: collision-free samples.
        samples: list[FloatArray] = []
        attempts = 0
        max_attempts = 200 * p.num_samples
        while len(samples) < p.num_samples and attempts < max_attempts:
            batch = sampler.uniform_batch(max(64, p.num_samples))
            attempts += len(batch)
            ok = batch[checker.points_free(batch)]
            samples.extend(ok[: p.num_samples - len(samples)])
        pts = np.vstack([np.asarray(problem.start), np.asarray(problem.goal), *samples])
        n = len(pts)
        for i, q in enumerate(pts[2:]):
            if i % 10 == 0:
                rec.step()
            rec.node(q, "roadmap")

        # Connect each vertex to its k nearest neighbors.
        k = min(p.k_neighbors, n - 1)
        adjacency: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        pairs: set[tuple[int, int]] = set()
        for i in range(n):
            d = np.linalg.norm(pts - pts[i], axis=1)
            d[i] = np.inf
            for j in np.argpartition(d, k - 1)[:k] if k > 0 else []:
                pairs.add((min(i, int(j)), max(i, int(j))))
        pair_arr = np.array(sorted(pairs), dtype=np.intp).reshape(-1, 2)
        free = (
            checker.segments_free(pts[pair_arr[:, 0]], pts[pair_arr[:, 1]])
            if len(pair_arr)
            else np.zeros(0, dtype=bool)
        )
        num_edges = 0
        last_i = -1
        for (i, j), ok in zip(pair_arr, free, strict=True):
            if not ok:
                continue
            i, j = int(i), int(j)
            w = float(np.linalg.norm(pts[i] - pts[j]))
            adjacency[i].append((j, w))
            adjacency[j].append((i, w))
            if i != last_i and i % 5 == 0:
                rec.step()
            last_i = i
            rec.edge(i * n + j, pts[i], pts[j], "roadmap")
            num_edges += 1

        # Query phase: A* from vertex 0 (start) to vertex 1 (goal).
        goal = pts[1]
        g = {0: 0.0}
        parent = {0: -1}
        heap = [(float(np.linalg.norm(goal - pts[0])), 0)]
        closed: set[int] = set()
        expansions = 0
        while heap:
            _, u = heapq.heappop(heap)
            if u in closed:
                continue
            closed.add(u)
            expansions += 1
            rec.step()
            rec.node(pts[u], "visited")
            if u == 1:
                break
            for v, w in adjacency[u]:
                cand = g[u] + w
                if cand < g.get(v, math.inf):
                    g[v] = cand
                    parent[v] = u
                    heapq.heappush(heap, (cand + float(np.linalg.norm(goal - pts[v])), v))

        stats = {
            "samples": len(samples),
            "roadmap_edges": num_edges,
            "expansions": expansions,
            "sampling_attempts": attempts,
        }
        if 1 not in closed:
            return PlanOutcome(
                None,
                "Start and goal are not connected by the roadmap. Try more samples or neighbors.",
                stats,
            )
        idx = [1]
        while idx[-1] != 0:
            idx.append(parent[idx[-1]])
        idx.reverse()
        path = [(float(pts[i, 0]), float(pts[i, 1])) for i in idx]
        return PlanOutcome(path, "", stats)
