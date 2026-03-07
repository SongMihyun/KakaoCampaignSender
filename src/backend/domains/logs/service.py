# FILE: src/backend/domains/logs/service.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.domains.logs.models import SendLog


class LogsService:
    """
    Logs 도메인 orchestration 계층.

    역할:
    - DB send_logs 조회/초기화
    - REPORT JSON -> row 변환 위임
    - REPORT row 필터링/재시도 대상 추출
    """

    def __init__(self, *, repo, report_reader=None) -> None:
        self.repo = repo
        self.report_reader = report_reader

    def list_logs(
        self,
        *,
        status: str | None = None,
        keyword: str = "",
        limit: int = 2000,
        offset: int = 0,
    ) -> list[SendLog]:
        rows = self.repo.list_logs(
            status=status,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
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

    def list_log_rows(
        self,
        *,
        status: str | None = None,
        keyword: str = "",
        limit: int = 2000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        logs = self.list_logs(
            status=status,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        return [self._send_log_to_row(log) for log in logs]

    def load_report_rows(
        self,
        path: str | Path,
        *,
        report_reader=None,
    ) -> List[Dict[str, Any]]:
        reader = report_reader or self.report_reader
        if reader is None:
            raise ValueError("report_reader가 설정되지 않았습니다.")

        obj = reader.load_json(path)
        return reader.build_rows(obj)

    def filter_report_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        status: str | None = None,
        keyword: str = "",
        report_reader=None,
    ) -> List[Dict[str, Any]]:
        reader = report_reader or self.report_reader
        if reader is not None and hasattr(reader, "filter_rows"):
            return reader.filter_rows(rows, status=status, keyword=keyword)

        status_norm = str(status or "").strip().upper()
        keyword_norm = str(keyword or "").strip().lower()

        out: List[Dict[str, Any]] = []
        for row in rows:
            row_status = str(row.get("status", "") or "").upper()

            if status_norm and not row_status.startswith(status_norm):
                continue

            if keyword_norm:
                hay = " ".join(
                    [
                        str(row.get("channel", "") or ""),
                        str(row.get("recipient", "") or ""),
                        str(row.get("reason", "") or ""),
                        str(row.get("_list_title", "") or ""),
                        str(row.get("_campaign_name", "") or ""),
                        str(row.get("_group_name", "") or ""),
                    ]
                ).lower()
                if keyword_norm not in hay:
                    continue

            out.append(row)

        return out

    def get_retry_targets(self) -> List[str]:
        return self.repo.get_retry_targets()

    def get_retry_targets_from_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        fail_prefix: str = "FAIL",
        report_reader=None,
    ) -> List[str]:
        reader = report_reader or self.report_reader
        if reader is not None and hasattr(reader, "build_retry_targets"):
            return reader.build_retry_targets(rows, fail_prefix=fail_prefix)

        prefix = str(fail_prefix or "FAIL").upper()
        targets: List[str] = []
        for row in rows:
            status = str(row.get("status", "") or "").upper()
            if not status.startswith(prefix):
                continue
            targets.append(
                f"{str(row.get('recipient', '') or '')} | {str(row.get('reason', '') or '')}"
            )
        return targets

    def reset_all(self) -> None:
        self.repo.reset_all()

    def _send_log_to_row(self, log: SendLog) -> Dict[str, Any]:
        return {
            "id": log.id,
            "ts": log.ts,
            "campaign_id": log.campaign_id,
            "batch_id": log.batch_id,
            "channel": log.channel,
            "recipient": log.recipient,
            "status": log.status,
            "reason": log.reason,
            "attempt": log.attempt,
            "message_len": log.message_len,
            "image_count": log.image_count,
        }