"""Recording planner execution for step-by-step visualization.

Planners report what they are doing through a :class:`Recorder`. Events are
small JSON arrays whose first element is a one-letter code; they are grouped
into *steps* (typically one iteration or node expansion) which the UI plays
back one at a time. See ``docs/trace-format.md`` for the full specification.

=====  ===================================  =========================================
Code   Arguments                            Meaning
=====  ===================================  =========================================
``X``  ``i, j``                             grid cell expanded (closed)
``F``  ``i, j``                             grid cell added to the open set (frontier)
``S``  ``x, y``                             random sample (transient, current step only)
``N``  ``x, y, layer``                      persistent vertex
``E``  ``key, x1, y1, x2, y2, layer``       add or replace the edge identified by ``key``
``R``  ``key``                              remove the edge identified by ``key``
``P``  ``[[x, y], ...]`` or ``null``        current best/candidate path (replaces previous)
``G``  ``key, geometry`` or ``key, null``   add/replace/remove an overlay shape
=====  ===================================  =========================================
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

#: A 2D point given as a sequence or a NumPy array.
PointLike = Sequence[float] | NDArray[np.float64]

#: Default cap on recorded events (keeps responses at a few tens of MB at most).
DEFAULT_MAX_EVENTS = 1_500_000

_DIGITS = 4


def _r(v: float) -> float:
    return round(float(v), _DIGITS)


def _key(key: Hashable) -> Any:
    return key if isinstance(key, (int, str)) else str(key)


class Recorder:
    """Collects visualization events emitted by a planner."""

    enabled = True

    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self.max_events = max_events
        self.events: list[list[Any]] = []
        self.steps: list[int] = []
        self.truncated = False
        self._started = False

    # ------------------------------------------------------------------ structure

    def step(self) -> None:
        """Start a new animation step.

        Events emitted before the first call (e.g. initializing the open set)
        belong to the first step.
        """
        if self.truncated:
            return
        if not self._started:
            self._started = True
            if self.steps:
                return
        n = len(self.events)
        if self.steps and self.steps[-1] == n:
            return  # previous step was empty: reuse it
        self.steps.append(n)

    def _emit(self, event: list[Any]) -> None:
        if self.truncated:
            return
        if len(self.events) >= self.max_events:
            self.truncated = True
            return
        if not self.steps:
            self.steps.append(0)
        self.events.append(event)

    # ------------------------------------------------------------------ grid search

    def expand(self, i: int, j: int) -> None:
        self._emit(["X", int(i), int(j)])

    def frontier(self, i: int, j: int) -> None:
        self._emit(["F", int(i), int(j)])

    # ------------------------------------------------------------------ geometry

    def sample(self, p: PointLike) -> None:
        self._emit(["S", _r(p[0]), _r(p[1])])

    def node(self, p: PointLike, layer: str = "tree") -> None:
        self._emit(["N", _r(p[0]), _r(p[1]), layer])

    def edge(self, key: Hashable, a: PointLike, b: PointLike, layer: str = "tree") -> None:
        self._emit(["E", _key(key), _r(a[0]), _r(a[1]), _r(b[0]), _r(b[1]), layer])

    def remove_edge(self, key: Hashable) -> None:
        self._emit(["R", _key(key)])

    def path(self, points: Iterable[PointLike] | None) -> None:
        if points is None:
            self._emit(["P", None])
        else:
            self._emit(["P", [[_r(p[0]), _r(p[1])] for p in points]])

    def overlay(self, key: Hashable, geometry: dict[str, Any] | None) -> None:
        self._emit(["G", _key(key), geometry])

    # ------------------------------------------------------------------ export

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": self.events,
            "steps": self.steps,
            "num_steps": len(self.steps),
            "truncated": self.truncated,
        }


class NullRecorder(Recorder):
    """A recorder that discards everything (used for benchmarking)."""

    enabled = False

    def step(self) -> None:
        pass

    def _emit(self, event: list[Any]) -> None:
        pass


@dataclass
class TraceState:
    """The accumulated visualization state after replaying a trace.

    Mirrors the logic of the web renderer; used by the matplotlib exporter
    and by tests that validate planner traces.
    """

    expanded: set[tuple[int, int]] = field(default_factory=set)
    frontier: set[tuple[int, int]] = field(default_factory=set)
    nodes: list[tuple[float, float, str]] = field(default_factory=list)
    edges: dict[Any, tuple[float, float, float, float, str]] = field(default_factory=dict)
    path: list[list[float]] | None = None
    overlays: dict[Any, dict[str, Any]] = field(default_factory=dict)
    sample: tuple[float, float] | None = None

    def apply(self, event: Sequence[Any]) -> None:
        code = event[0]
        if code == "X":
            cell = (event[1], event[2])
            self.frontier.discard(cell)
            self.expanded.add(cell)
        elif code == "F":
            cell = (event[1], event[2])
            if cell not in self.expanded:
                self.frontier.add(cell)
        elif code == "S":
            self.sample = (event[1], event[2])
        elif code == "N":
            self.nodes.append((event[1], event[2], event[3]))
        elif code == "E":
            self.edges[event[1]] = (event[2], event[3], event[4], event[5], event[6])
        elif code == "R":
            self.edges.pop(event[1], None)
        elif code == "P":
            self.path = event[1]
        elif code == "G":
            if event[2] is None:
                self.overlays.pop(event[1], None)
            else:
                self.overlays[event[1]] = event[2]
        else:
            raise ValueError(f"unknown trace event code {code!r}")

    @classmethod
    def replay(cls, trace: dict[str, Any], upto_step: int | None = None) -> TraceState:
        """Replay ``trace`` (as produced by :meth:`Recorder.to_dict`) up to a step."""
        state = cls()
        events = trace["events"]
        steps = trace["steps"]
        end = len(events)
        if upto_step is not None and upto_step + 1 < len(steps):
            end = steps[upto_step + 1]
        for event in events[:end]:
            state.apply(event)
        return state
