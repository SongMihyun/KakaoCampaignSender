from __future__ import annotations

from backend.domains.campaigns.dto import CampaignDraftItemDTO
from backend.domains.campaigns.models import Campaign, CampaignItem


class CampaignsService:
    def __init__(self, *, repo) -> None:
        self.repo = repo

    def list_campaigns(self) -> list[Campaign]:
        rows = self.repo.list_campaigns()
        return [Campaign(id=int(r.id), name=str(r.name)) for r in rows]

    def get_campaign_items(self, campaign_id: int) -> list[CampaignItem]:
        rows = self.repo.get_campaign_items(int(campaign_id))
        return [
            CampaignItem(
                id=int(getattr(r, "id", 0) or 0),
                campaign_id=int(getattr(r, "campaign_id", campaign_id) or campaign_id),
                item_type=str(getattr(r, "item_type", "") or "").upper(),
                text=str(getattr(r, "text", "") or ""),
                image_name=str(getattr(r, "image_name", "") or ""),
                image_bytes=getattr(r, "image_bytes", b"") or b"",
                sort_order=int(getattr(r, "sort_order", 0) or 0),
            )
            for r in rows
        ]

    def create_campaign(self, name: str, draft_items: list[CampaignDraftItemDTO]) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("캠페인명은 필수입니다.")
        if not draft_items:
            raise ValueError("저장할 캠페인 아이템이 없습니다.")

        payload = []
        for it in draft_items:
            typ = str(it.item_type or "").upper().strip()
            if typ == "TEXT":
                payload.append(("TEXT", {"text": (it.text or "").strip()}))
            else:
                payload.append(("IMAGE", {
                    "image_name": (it.image_name or "").strip(),
                    "image_bytes": it.image_bytes or b"",
                }))
        return int(self.repo.create_campaign(name, payload))

    def delete_campaign(self, campaign_id: int) -> None:
        self.repo.delete_campaign(int(campaign_id))