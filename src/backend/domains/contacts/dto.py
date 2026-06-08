from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class ContactCreateDTO:
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None


@dataclass(slots=True)
class ContactUpdateDTO:
    row_id: int = 0
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None
