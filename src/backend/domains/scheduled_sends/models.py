# FILE: src/backend/domains/scheduled_sends/models.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScheduledSendRow:
    id: int
    planned_at: str
    status: str
    speed_mode: str
    send_list_snapshot_json: str
    task_name: str
    task_path: str
    launched_at: str
    finished_at: str
    last_error: str
    created_at: str
