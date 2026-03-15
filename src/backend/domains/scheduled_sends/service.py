# FILE: src/backend/domains/scheduled_sends/service.py
from __future__ import annotations

import json
from datetime import datetime

from .repository import ScheduledSendsRepo
from backend.integrations.windows.task_scheduler_service import TaskSchedulerService


class ScheduledSendsService:
    def __init__(
        self,
        *,
        repo: ScheduledSendsRepo,
        task_scheduler: TaskSchedulerService,
    ) -> None:
        self.repo = repo
        self.task_scheduler = task_scheduler

    def create_schedule(
        self,
        *,
        planned_at: datetime,
        speed_mode: str,
        send_list_rows: list[dict],
        executable_path: str,
        arguments: list[str],
        working_dir: str,
    ) -> int:
        snapshot_json = json.dumps(send_list_rows, ensure_ascii=False)

        schedule_id = self.repo.create_pending(
            planned_at=planned_at.strftime("%Y-%m-%d %H:%M:%S"),
            speed_mode=str(speed_mode or "normal"),
            send_list_snapshot_json=snapshot_json,
        )

        task = self.task_scheduler.register_one_time_task(
            schedule_id=schedule_id,
            run_at=planned_at,
            executable_path=executable_path,
            arguments=arguments + [
                "--scheduled-send-id", str(schedule_id),
                "--scheduler-launch",
                "--minimized",
            ],
            working_dir=working_dir,
            description=f"Kakao Campaign Sender scheduled send #{schedule_id}",
        )

        self.repo.attach_task_info(
            schedule_id,
            task_name=task.task_name,
            task_path=task.task_path,
        )
        return schedule_id

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

        row = self.repo.get(schedule_id)
        if row and row.task_name:
            try:
                self.task_scheduler.delete_task(row.task_name)
            except Exception:
                pass

    def mark_failed(self, schedule_id: int, error_text: str) -> None:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.mark_failed(schedule_id, now_text, error_text)

    def cancel_schedule(self, schedule_id: int) -> None:
        row = self.repo.get(schedule_id)
        if row and row.task_name:
            try:
                self.task_scheduler.delete_task(row.task_name)
            except Exception:
                pass
        self.repo.cancel(schedule_id)

    def list_due_pending(self) -> list:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.repo.list_due_pending(now_text)

    def get_latest_actionable(self):
        return self.repo.get_latest_actionable()
