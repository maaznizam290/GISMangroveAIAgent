"""Small result type shared by CRS checks, AOI review and milestone gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def worst(checks: list[Check]) -> Status:
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return max((c.status for c in checks), key=order.__getitem__, default="PASS")
