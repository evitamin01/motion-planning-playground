"""Declarative, self-describing parameters.

Planner (and generator) parameters are plain dataclasses whose fields are
declared with :func:`param`. The metadata attached to each field drives
validation, the JSON schema served to the web UI (which renders a form from
it), and CLI parsing - so a new planner only has to declare its parameters once.

Example::

    @dataclass
    class Params(ParamsBase):
        step_size: float = param(2.0, min=0.1, max=20.0, help="Maximum edge length.")
        heuristic: str = param("euclidean", choices=["euclidean", "manhattan"])
"""

from __future__ import annotations

import dataclasses
import math
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T", bound="ParamsBase")

_TYPE_NAMES = {bool: "bool", int: "int", float: "float", str: "str"}


def param(
    default: Any,
    *,
    min: float | None = None,
    max: float | None = None,
    step: float | None = None,
    choices: Sequence[str] | None = None,
    label: str | None = None,
    help: str = "",
    advanced: bool = False,
) -> Any:
    """Declare a parameter field with UI/validation metadata."""
    meta = {
        "min": min,
        "max": max,
        "step": step,
        "choices": list(choices) if choices is not None else None,
        "label": label,
        "help": help,
        "advanced": advanced,
    }
    return dataclasses.field(default=default, metadata={"mpplay": meta})


@dataclass
class ParamsBase:
    """Base class for parameter dataclasses."""

    @classmethod
    def _fields(cls) -> list[tuple[dataclasses.Field[Any], type, dict[str, Any]]]:
        hints = typing.get_type_hints(cls)
        out = []
        for f in dataclasses.fields(cls):
            typ = hints[f.name]
            if typ not in _TYPE_NAMES:
                raise TypeError(f"unsupported parameter type {typ!r} for {cls.__name__}.{f.name}")
            out.append((f, typ, f.metadata.get("mpplay", {})))
        return out

    @classmethod
    def schema(cls) -> list[dict[str, Any]]:
        """Describe the parameters as a list of JSON-serializable field specs."""
        specs = []
        for f, typ, meta in cls._fields():
            kind = "choice" if meta.get("choices") else _TYPE_NAMES[typ]
            spec: dict[str, Any] = {
                "name": f.name,
                "type": kind,
                "default": f.default,
                "label": meta.get("label") or f.name.replace("_", " ").capitalize(),
                "help": meta.get("help", ""),
                "advanced": bool(meta.get("advanced", False)),
            }
            for key in ("min", "max", "step", "choices"):
                if meta.get(key) is not None:
                    spec[key] = meta[key]
            specs.append(spec)
        return specs

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any] | None = None, *, strict: bool = True) -> T:
        """Build validated parameters from a mapping, filling in defaults.

        Values are coerced to the declared type (e.g. ``"3"`` -> ``3`` for CLI input)
        and checked against ``min``/``max``/``choices``. Unknown keys raise
        :class:`ValueError` when ``strict`` is true and are ignored otherwise.
        """
        data = dict(data or {})
        values: dict[str, Any] = {}
        for f, typ, meta in cls._fields():
            if f.name not in data:
                continue
            values[f.name] = _coerce(cls.__name__, f.name, data.pop(f.name), typ, meta)
        if data and strict:
            known = ", ".join(f.name for f in dataclasses.fields(cls)) or "none"
            raise ValueError(f"unknown parameter(s) {sorted(data)}; known parameters: {known}")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _coerce(owner: str, name: str, value: Any, typ: type, meta: dict[str, Any]) -> Any:
    where = f"{owner}.{name}"
    try:
        if typ is bool:
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                    raise ValueError
                value = lowered in {"true", "1", "yes", "on"}
            else:
                value = bool(value)
        elif typ is int:
            as_float = float(value)
            if not as_float.is_integer():
                raise ValueError
            value = int(as_float)
        elif typ is float:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError
        else:
            value = str(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: cannot interpret {value!r} as {_TYPE_NAMES[typ]}") from None

    choices = meta.get("choices")
    if choices is not None and value not in choices:
        raise ValueError(f"{where}: {value!r} is not one of {choices}")
    lo, hi = meta.get("min"), meta.get("max")
    if lo is not None and value < lo:
        raise ValueError(f"{where}: {value} is below the minimum {lo}")
    if hi is not None and value > hi:
        raise ValueError(f"{where}: {value} is above the maximum {hi}")
    return value


@dataclass
class NoParams(ParamsBase):
    """Placeholder for components without parameters."""
