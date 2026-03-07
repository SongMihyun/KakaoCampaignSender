from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CampaignItemType = Literal["TEXT", "IMAGE"]


@dataclass(slots=True)
class Campaign:
    id: int
    name: str


@dataclass(slots=True)
class CampaignItem:
    id: int
    campaign_id: int
    item_type: CampaignItemType
    text: str = ""
    image_name: str = ""
    image_bytes: bytes = b""
    sort_order: int = 0