# FILE: src/backend/domains/scheduled_sends/service.py
from __future__ import annotations

import json
from datetime import datetime

from .repository import ScheduledSendsRepo


class ScheduledSendsService:
    def __init__(
        self,
        *,
        repo: ScheduledSendsRepo,
    ) -> None:
        self.repo = repo

    def create_schedule(
        self,
        *,
        planned_at: datetime,
        speed_mode: str,
        send_list_rows: list[dict],
    ) -> tuple[int, bool]:
        snapshot_json = json.dumps(send_list_rows, ensure_ascii=False)
        return self.repo.create_pending(
            planned_at=planned_at.strftime("%Y-%m-%d %H:%M:%S"),
            speed_mode=str(speed_mode or "normal"),
            send_list_snapshot_json=snapshot_json,
        )

    def get_schedule(self, schedule_id: int):
        return self.repo.get(schedule_id)

    def get_snapshot_rows(self, schedule_id: int) -> list[dict]:
        row = self.repo.get(schedule_id)
        if not row:
            raise ValueError("예약 정보를 찾을 수 없습니다.")
        return json.loads(row.send_list_snapshot_json or "[]")

    def mark_running_if_pending(self, schedule_id: int) -> bool:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.repo.mark_running_if_pending(schedule_id, now_text)

    def mark_done(self, schedule_id: int) -> None:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.mark_done(schedule_id, now_text)

    def mark_failed(self, schedule_id: int, error_text: str) -> None:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.mark_failed(schedule_id, now_text, error_text)

    def cancel_schedule(self, schedule_id: int) -> None:
        self.repo.cancel(schedule_id)

    def list_due_pending(self) -> list:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.repo.list_due_pending(now_text)

    def get_latest_actionable(self):
        return self.repo.get_latest_actionable()
