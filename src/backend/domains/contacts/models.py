from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class Contact:
    id: int
    emp_id: str
    name: str
    customer_name: str = ""
    customer_honorific: str = "고객님"
    customer_position: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    customer_status: str = ""
    tags: str = ""
    memo2: str = ""
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None
