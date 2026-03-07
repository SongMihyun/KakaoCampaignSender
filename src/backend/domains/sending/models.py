from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Recipient:
    contact_id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str


@dataclass(slots=True)
class SendJob:
    send_list_id: int
    title: str
    group_name: str
    campaign_id: int
    campaign_name: str
    recipients: list[Recipient]
    recipients_snapshot: list[dict]
    campaign_items: list[Any]