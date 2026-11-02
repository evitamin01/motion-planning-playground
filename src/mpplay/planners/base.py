"""Planner interface and registry.

Implementing a planner takes three steps:

1. Subclass :class:`Planner` and fill in the descriptive class attributes.
2. Declare parameters as a nested ``Params`` dataclass (see :mod:`mpplay.params`).
3. Implement :meth:`Planner.plan` and decorate the class with :func:`register_planner`.

The planner then shows up automatically in the CLI, the HTTP API and the web UI
(including an auto-generated parameter form). See ``docs/adding-a-planner.md``.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TypeVar

import numpy as np

from ..environment import Problem
from ..geometry import Point
from ..params import NoParams, ParamsBase
from ..trace import Recorder

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "mpplay.planners"


class PlanningError(Exception):
    """Raised by planners to abort with a user-facing failure message."""


@dataclass
class PlanOutcome:
    """What a planner returns.

    Attributes:
        path: Waypoints from start to goal, or ``None`` if no path was found.
        message: Short human-readable status (shown in the UI).
        stats: Planner-specific counters (e.g. ``expansions``, ``tree_size``).
        series: Named time series, e.g. ``{"best_cost": [[iteration, cost], ...]}``.
        overlays: Static visualization layers (e.g. potential-field heatmaps).
    """

    path: list[Point] | None
    message: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    series: dict[str, list[list[float]]] = field(default_factory=dict)
    overlays: list[dict[str, Any]] = field(default_factory=list)


class Planner(ABC):
    """Base class of all motion planners.

    Class attributes describe the planner for the UI and documentation.
    """

    #: Unique registry key (lower_snake_case), e.g. ``"astar"``.
    name: ClassVar[str]
    #: Display name, e.g. ``"A*"``.
    label: ClassVar[str]
    #: Algorithm family used to group planners in the UI.
    family: ClassVar[str] = "Other"
    #: One-sentence summary.
    summary: ClassVar[str] = ""
    #: Longer explanation of how the algorithm works (plain text; blank lines separate paragraphs).
    description: ClassVar[str] = ""
    #: Key properties, e.g. ``{"Complete": "resolution complete", "Optimal": "yes"}``.
    properties: ClassVar[dict[str, str]] = {}
    #: Literature references.
    references: ClassVar[list[str]] = []
    #: Whether the planner works on the rasterized occupancy grid.
    uses_grid: ClassVar[bool] = False
    #: Whether results depend on the random seed.
    stochastic: ClassVar[bool] = False
    #: Parameter dataclass.
    Params: ClassVar[type[ParamsBase]] = NoParams

    def __init__(self, params: Mapping[str, Any] | ParamsBase | None = None) -> None:
        if isinstance(params, ParamsBase):
            if not isinstance(params, self.Params):
                raise TypeError(f"expected {self.Params.__name__}, got {type(params).__name__}")
            self.params: Any = params
        else:
            self.params = self.Params.from_dict(params)

    def setup(self, problem: Problem) -> None:  # noqa: B027 - optional hook
        """Untimed preprocessing shared across runs (e.g. rasterization)."""

    @abstractmethod
    def plan(self, problem: Problem, rng: np.random.Generator, rec: Recorder) -> PlanOutcome:
        """Solve ``problem`` and report progress to ``rec``."""

    @classmethod
    def info(cls) -> dict[str, Any]:
        """JSON-serializable description used by the API and UI."""
        return {
            "name": cls.name,
            "label": cls.label,
            "family": cls.family,
            "summary": cls.summary,
            "description": cls.description.strip(),
            "properties": dict(cls.properties),
            "references": list(cls.references),
            "uses_grid": cls.uses_grid,
            "stochastic": cls.stochastic,
            "params": cls.Params.schema(),
        }


P = TypeVar("P", bound=type[Planner])

_REGISTRY: dict[str, type[Planner]] = {}
_PLUGINS_LOADED = False


def register_planner(cls: P) -> P:
    """Class decorator that makes a planner available everywhere."""
    for attr in ("name", "label"):
        if not getattr(cls, attr, None):
            raise TypeError(f"{cls.__name__} must define a non-empty '{attr}' class attribute")
    existing = _REGISTRY.get(cls.name)
    if existing is not None and existing is not cls:
        raise ValueError(f"a planner named {cls.name!r} is already registered ({existing})")
    _REGISTRY[cls.name] = cls
    return cls


def unregister_planner(name: str) -> None:
    _REGISTRY.pop(name, None)


def get_planner(name: str) -> type[Planner]:
    load_plugins()
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"unknown planner {name!r}; available: {known}") from None


def available_planners() -> list[type[Planner]]:
    """Registered planners in registration order."""
    load_plugins()
    return list(_REGISTRY.values())


def load_plugins() -> None:
    """Import third-party planners advertised via the ``mpplay.planners`` entry point group."""
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            ep.load()
        except Exception:  # pragma: no cover - depends on installed plugins
            log.exception("failed to load planner plugin %s", ep.name)


def import_plugin_module(spec: str) -> None:
    """Import a module (dotted name or ``path/to/file.py``) that registers planners."""
    if spec.endswith(".py"):
        path = Path(spec).resolve()
        module_name = f"mpplay_plugin_{path.stem}"
        module_spec = importlib.util.spec_from_file_location(module_name, path)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"cannot import plugin file {spec}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)
    else:
        importlib.import_module(spec)
