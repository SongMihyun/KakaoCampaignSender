from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class Group:
    id: int
    name: str
    memo: str = ""