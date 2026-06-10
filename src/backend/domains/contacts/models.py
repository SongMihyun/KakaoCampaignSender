from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class Contact:
    id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str