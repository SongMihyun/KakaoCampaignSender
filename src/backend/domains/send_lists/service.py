from __future__ import annotations

from backend.domains.send_lists.dto import SendListCreateDTO
from backend.domains.send_lists.models import SendList


class SendListsService:
    def __init__(self, *, repo) -> None:
        self.repo = repo

    def list_send_lists(self) -> list[SendList]:
        rows = self.repo.list_send_lists()
        return [
            SendList(
                id=int(getattr(r, "id")),
                target_mode=str(getattr(r, "target_mode", "") or "").upper(),
                group_id=(int(getattr(r, "group_id")) if getattr(r, "group_id", None) is not None else None),
                group_name=str(getattr(r, "group_name", "") or ""),
                campaign_id=int(getattr(r, "campaign_id")),
                campaign_name=str(getattr(r, "campaign_name", "") or ""),
                sort_order=int(getattr(r, "sort_order", 0) or 0),
            )
            for r in rows
        ]

    def create_or_replace(self, dto: SendListCreateDTO) -> int:
        return int(
            self.repo.create_or_replace_send_list(
                target_mode=str(dto.target_mode or "").upper(),
                group_id=(int(dto.group_id) if dto.group_id is not None else None),
                group_name=(dto.group_name or "").strip(),
                campaign_id=int(dto.campaign_id),
                campaign_name=(dto.campaign_name or "").strip(),
            )
        )

    def get_meta(self, send_list_id: int):
        return self.repo.get_send_list_meta(int(send_list_id))

    def delete_send_list(self, send_list_id: int) -> None:
        self.repo.delete_send_list(int(send_list_id))

    def update_orders(self, ordered_ids: list[int]) -> None:
        self.repo.update_send_list_orders([int(x) for x in ordered_ids or []])