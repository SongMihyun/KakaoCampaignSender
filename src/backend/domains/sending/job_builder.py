from __future__ import annotations

from backend.domains.sending.models import SendJob
from backend.domains.sending.resolver import (
    resolve_contacts_for_send_list_meta,
    build_recipients_and_snapshot,
)


class SendJobBuilder:
    def __init__(
        self,
        *,
        send_lists_service,
        groups_repo,
        contacts_store,
        campaigns_service,
    ) -> None:
        self.send_lists_service = send_lists_service
        self.groups_repo = groups_repo
        self.contacts_store = contacts_store
        self.campaigns_service = campaigns_service

    def build_all_jobs(self, send_list_rows: list[dict]) -> list[SendJob]:
        jobs: list[SendJob] = []

        for data in send_list_rows or []:
            send_list_id = int(data["send_list_id"])
            title = str(data["title"])
            group_name = str(data["group_name"])
            campaign_id = int(data["campaign_id"])
            campaign_name = str(data["campaign_name"])

            meta = self.send_lists_service.get_meta(send_list_id)
            if not meta:
                continue

            contacts_mem = resolve_contacts_for_send_list_meta(
                contacts_store=self.contacts_store,
                groups_repo=self.groups_repo,
                target_mode=str(getattr(meta, "target_mode", "") or ""),
                group_id=getattr(meta, "group_id", None),
            )

            recipients, recipients_snapshot = build_recipients_and_snapshot(contacts_mem)

            campaign = self.campaigns_service.get_campaign(campaign_id)
            campaign_items = self.campaigns_service.get_campaign_items(campaign_id)
            send_mode = str(getattr(campaign, "send_mode", "clipboard") or "clipboard")

            jobs.append(
                SendJob(
                    send_list_id=send_list_id,
                    title=title,
                    group_name=group_name,
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    send_mode=send_mode,
                    recipients=recipients,
                    recipients_snapshot=recipients_snapshot,
                    campaign_items=campaign_items,
                )
            )

        return jobs