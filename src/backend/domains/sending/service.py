# FILE: src/backend/domains/sending/service.py
from __future__ import annotations

from backend.domains.send_lists.dto import SendListCreateDTO
from backend.domains.sending.executor import SendExecutor
from backend.domains.sending.job_builder import SendJobBuilder
from backend.domains.sending.models import Recipient
from backend.domains.sending.resolver import (
    build_recipients_and_snapshot,
    resolve_contacts_for_send_list_meta,
)
from backend.domains.sending.worker import MultiSendWorker


class SendingService:
    def __init__(self, *, job_builder: SendJobBuilder) -> None:
        self.job_builder = job_builder

    def build_jobs(self, send_list_rows: list[dict]):
        return self.job_builder.build_all_jobs(send_list_rows)

    def create_executor(self, **kwargs) -> SendExecutor:
        return SendExecutor(**kwargs)

    def create_worker(self, **kwargs) -> MultiSendWorker:
        return MultiSendWorker(**kwargs)

    def list_groups(self):
        return self.job_builder.groups_repo.list_groups()

    def list_send_lists(self):
        return self.job_builder.send_lists_service.list_send_lists()

    def get_send_list_meta(self, send_list_id: int):
        return self.job_builder.send_lists_service.get_meta(int(send_list_id))

    def delete_send_list(self, send_list_id: int) -> None:
        self.job_builder.send_lists_service.delete_send_list(int(send_list_id))

    def update_send_list_orders(self, ordered_ids: list[int]) -> None:
        self.job_builder.send_lists_service.update_orders(ordered_ids)

    def resolve_contacts_for_meta(self, *, target_mode: str, group_id):
        return resolve_contacts_for_send_list_meta(
            contacts_store=self.job_builder.contacts_store,
            groups_repo=self.job_builder.groups_repo,
            target_mode=target_mode,
            group_id=group_id,
        )

    def build_recipients_and_snapshot_for_meta(
        self,
        *,
        target_mode: str,
        group_id,
    ) -> tuple[list[Recipient], list[dict]]:
        contacts_mem = self.resolve_contacts_for_meta(
            target_mode=target_mode,
            group_id=group_id,
        )
        return build_recipients_and_snapshot(contacts_mem)

    def create_or_replace_send_list(self, dto: SendListCreateDTO) -> tuple[int, int]:
        target_mode = str(dto.target_mode or "").upper().strip()
        group_id = int(dto.group_id) if dto.group_id is not None else None

        recipients, _snapshot = self.build_recipients_and_snapshot_for_meta(
            target_mode=target_mode,
            group_id=group_id,
        )
        if not recipients:
            raise ValueError("대상자가 없습니다.")

        send_list_id = self.job_builder.send_lists_service.create_or_replace(
            SendListCreateDTO(
                target_mode=target_mode,
                group_id=group_id,
                group_name=(dto.group_name or "").strip(),
                campaign_id=int(dto.campaign_id),
                campaign_name=(dto.campaign_name or "").strip(),
            )
        )
        return int(send_list_id), len(recipients)

    def build_preview_rows(self, send_list_id: int) -> tuple[list[dict], str]:
        meta = self.get_send_list_meta(int(send_list_id))
        if not meta:
            return [], ""

        target_mode = str(getattr(meta, "target_mode", "") or "").upper()
        group_id = getattr(meta, "group_id", None)

        contacts_mem = self.resolve_contacts_for_meta(
            target_mode=target_mode,
            group_id=group_id,
        )

        rows: list[dict] = []
        shown = 0
        for m in contacts_mem or []:
            raw_name = str(getattr(m, "name", "") or "")
            name = raw_name.strip().replace("\u200b", "").replace("\ufeff", "")
            if not name:
                continue

            shown += 1
            rows.append(
                {
                    "no": shown,
                    "contact_id": int(getattr(m, "id", 0) or 0),
                    "emp_id": str(getattr(m, "emp_id", "") or ""),
                    "name": name,
                    "phone": str(getattr(m, "phone", "") or ""),
                    "agency": str(getattr(m, "agency", "") or ""),
                    "branch": str(getattr(m, "branch", "") or ""),
                }
            )

        title = self._format_title(
            str(getattr(meta, "group_name", "") or ""),
            str(getattr(meta, "campaign_name", "") or ""),
        )
        return rows, title

    @staticmethod
    def _format_title(group_name: str, campaign_name: str) -> str:
        group_name = (group_name or "").strip()
        campaign_name = (campaign_name or "").strip()
        return f"{group_name} + {campaign_name}".strip(" +")