from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal

TargetMode = Literal["ALL", "GROUP"]


@dataclass(slots=True)
class SendListCreateDTO:
    target_mode: TargetMode
    group_id: Optional[int]
    group_name: str
    campaign_id: int
    campaign_name: str