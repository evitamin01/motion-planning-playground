from __future__ import annotations

from dataclasses import dataclass

import pytest

from mpplay.params import ParamsBase, param


@dataclass
class Example(ParamsBase):
    count: int = param(10, min=1, max=100, help="How many.")
    rate: float = param(0.5, min=0.0, max=1.0, step=0.05)
    mode: str = param("a", choices=["a", "b"])
    flag: bool = param(False, advanced=True)


def test_defaults():
    p = Example.from_dict(None)
    assert p.to_dict() == {"count": 10, "rate": 0.5, "mode": "a", "flag": False}


def test_coercion_from_strings():
    p = Example.from_dict({"count": "7", "rate": "0.25", "mode": "b", "flag": "yes"})
    assert (p.count, p.rate, p.mode, p.flag) == (7, 0.25, "b", True)
    assert Example.from_dict({"count": 3.0}).count == 3


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"count": 0}, "below the minimum"),
        ({"count": 101}, "above the maximum"),
        ({"count": 2.5}, "as int"),
        ({"rate": "fast"}, "as float"),
        ({"rate": float("inf")}, "as float"),
        ({"mode": "c"}, "not one of"),
        ({"flag": "maybe"}, "as bool"),
        ({"unknown": 1}, "unknown parameter"),
    ],
)
def test_validation_errors(data, message):
    with pytest.raises(ValueError, match=message):
        Example.from_dict(data)


def test_non_strict_ignores_unknown():
    assert Example.from_dict({"unknown": 1}, strict=False).count == 10


def test_schema():
    schema = {s["name"]: s for s in Example.schema()}
    assert schema["count"]["type"] == "int"
    assert schema["count"]["min"] == 1
    assert schema["count"]["help"] == "How many."
    assert schema["mode"]["type"] == "choice"
    assert schema["mode"]["choices"] == ["a", "b"]
    assert schema["flag"]["advanced"] is True
    assert schema["rate"]["label"] == "Rate"
