"""Example plugin: the Expansive Space Tree (EST) planner.

This file shows everything needed to add a planner to the playground. Load it
into the web UI or the CLI with ``--plugin``::

    mpplay --plugin examples/est_planner.py serve
    mpplay --plugin examples/est_planner.py plan -s bug_trap -p est

The planner then appears in the planner list, with a parameter form generated
from ``Params``, step-by-step animation from the recorded events, and all the
usual metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from mpplay import Planner, PlanOutcome, Problem, Recorder, register_planner
from mpplay.params import ParamsBase, param


@register_planner
class EST(Planner):
    # --- metadata shown in the UI ("Learn" tab) and by `mpplay planners` -------------
    name = "est"
    label = "EST (plugin)"
    family = "Sampling-based"
    summary = "Expansive Space Tree: grows the tree from nodes in sparsely explored regions."
    description = """
EST grows a tree from the start. In each iteration it picks a tree node with a
probability inversely proportional to how many other nodes are nearby, then
tries to add a random point close to that node. Sparse regions are therefore
expanded preferentially, so the tree spreads out over the free space. As the
expansion is purely local and not biased towards the goal, EST needs many
iterations in long, winding corridors such as the maze or the office.

This planner is not built in: it is loaded from examples/est_planner.py to
demonstrate the plugin interface.
"""
    properties = {"Complete": "Probabilistically complete", "Optimal": "No", "Space": "Continuous"}
    references = [
        "D. Hsu, J.-C. Latombe, R. Motwani, 'Path planning in expansive configuration "
        "spaces', ICRA, 1997.",
    ]
    stochastic = True

    # --- parameters: validated, documented and rendered as a form automatically -------
    @dataclass
    class Params(ParamsBase):
        max_iterations: int = param(
            5000, min=10, max=50_000, step=100, label="Max iterations", help="Sampling budget."
        )
        radius: float = param(
            8.0,
            min=0.1,
            max=50.0,
            step=0.1,
            label="Expansion radius",
            help="New points are sampled within this distance of the chosen node.",
        )

    # --- the algorithm -----------------------------------------------------------------
    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        p = self.params
        checker = problem.checker  # exact collision checks for the disc robot
        goal = np.asarray(problem.goal, dtype=float)
        nodes = np.zeros((p.max_iterations + 2, 2))
        nodes[0] = problem.start
        parents = np.full(p.max_iterations + 2, -1)
        density = np.ones(p.max_iterations + 2)
        n = 1

        for it in range(1, p.max_iterations + 1):
            rec.step()  # one animation step per iteration
            weights = 1.0 / density[:n]
            k = int(rng.choice(n, p=weights / weights.sum()))
            angle = rng.uniform(0, 2 * math.pi)
            r = p.radius * math.sqrt(rng.random())
            q = nodes[k] + r * np.array([math.cos(angle), math.sin(angle)])
            rec.sample(q)  # transient marker
            if not checker.segment_free(nodes[k], q):
                continue
            near = np.linalg.norm(nodes[:n] - q, axis=1) < p.radius
            density[:n] += near
            nodes[n], parents[n], density[n] = q, k, 1 + near.sum()
            rec.edge(n, nodes[k], q)  # edges are keyed so they could be replaced later
            n += 1
            if np.linalg.norm(goal - q) <= p.radius and checker.segment_free(q, goal):
                path = [problem.goal]
                i = n - 1
                while i >= 0:
                    path.append((float(nodes[i, 0]), float(nodes[i, 1])))
                    i = int(parents[i])
                return PlanOutcome(path[::-1], stats={"iterations": it, "tree_size": n})

        return PlanOutcome(
            None,
            f"No path found within {p.max_iterations} iterations.",
            stats={"iterations": p.max_iterations, "tree_size": n},
        )
