from __future__ import annotations

from dataclasses import dataclass, field
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
    send_mode: str = "clipboard"
    recipients: list[Any] = field(default_factory=list)
    recipients_snapshot: list[dict] = field(default_factory=list)
    campaign_items: list[Any] = field(default_factory=list)