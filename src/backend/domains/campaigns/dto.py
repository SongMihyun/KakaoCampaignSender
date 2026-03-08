from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CampaignItemType = Literal["TEXT", "IMAGE"]
CampaignSendMode = Literal["clipboard", "multi_attach"]


@dataclass(slots=True)
class CampaignDraftItemDTO:
    item_type: CampaignItemType
    text: str = ""
    image_name: str = ""
    image_bytes: bytes = b""
    image_path: str = ""