from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class ContactCreateDTO:
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""


@dataclass(slots=True)
class ContactUpdateDTO:
    row_id: int = 0
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""