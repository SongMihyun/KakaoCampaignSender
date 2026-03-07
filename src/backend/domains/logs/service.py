from __future__ import annotations

from backend.domains.logs.models import SendLog


class LogsService:
    def __init__(self, *, repo) -> None:
        self.repo = repo

    def list_logs(self, *, status=None, keyword="", limit=2000, offset=0) -> list[SendLog]:
        rows = self.repo.list_logs(status=status, keyword=keyword, limit=limit, offset=offset)
        return [
            SendLog(
                id=int(r.id),
                ts=str(r.ts or ""),
                campaign_id=int(r.campaign_id or 0),
                batch_id=str(r.batch_id or ""),
                channel=str(r.channel or ""),
                recipient=str(r.recipient or ""),
                status=str(r.status or ""),
                reason=str(r.reason or ""),
                attempt=int(r.attempt or 0),
                message_len=int(r.message_len or 0),
                image_count=int(r.image_count or 0),
            )
            for r in rows
        ]

    def get_retry_targets(self):
        return self.repo.get_retry_targets()

    def reset_all(self):
        self.repo.reset_all()