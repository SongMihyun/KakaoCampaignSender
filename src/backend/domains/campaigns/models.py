from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CampaignItemType = Literal["TEXT", "IMAGE"]
CampaignSendMode = Literal["clipboard", "multi_attach"]


@dataclass(slots=True)
class Campaign:
    id: int
    name: str
    send_mode: CampaignSendMode = "clipboard"


@dataclass(slots=True)
class CampaignItem:
    id: int
    campaign_id: int
    item_type: CampaignItemType
    text: str = ""
    image_name: str = ""
    image_bytes: bytes = b""
    image_path: str = ""
    sort_order: int = 0