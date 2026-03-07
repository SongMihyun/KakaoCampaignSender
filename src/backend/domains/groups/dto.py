from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class GroupCreateDTO:
    name: str
    memo: str = ""


@dataclass(slots=True)
class GroupUpdateDTO:
    group_id: int
    name: str
    memo: str = ""