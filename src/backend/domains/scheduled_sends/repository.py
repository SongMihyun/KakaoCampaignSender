# FILE: src/backend/domains/scheduled_sends/repository.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .models import ScheduledSendRow


class ScheduledSendsRepo:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(Path(db_path))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass
        return conn

    def create_pending(
        self,
        *,
        planned_at: str,
        speed_mode: str,
        send_list_snapshot_json: str,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scheduled_sends(
                    planned_at,
                    status,
                    speed_mode,
                    send_list_snapshot_json
                )
                VALUES (?, 'PENDING', ?, ?);
                """,
                (planned_at, speed_mode, send_list_snapshot_json),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def attach_task_info(
        self,
        schedule_id: int,
        *,
        task_name: str,
        task_path: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_sends
                SET task_name=?, task_path=?
                WHERE id=?;
                """,
                (task_name, task_path, int(schedule_id)),
            )
            conn.commit()

    def get(self, schedule_id: int) -> Optional[ScheduledSendRow]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_sends WHERE id=?;",
                (int(schedule_id),),
            ).fetchone()
            if not row:
                return None
            return ScheduledSendRow(**dict(row))

    def get_latest_actionable(self) -> Optional[ScheduledSendRow]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM scheduled_sends
                WHERE status IN ('PENDING', 'FAILED', 'RUNNING')
                ORDER BY id DESC
                LIMIT 1;
                """
            ).fetchone()
            if not row:
                return None
            return ScheduledSendRow(**dict(row))

    def list_due_pending(self, now_text: str) -> list[ScheduledSendRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM scheduled_sends
                WHERE status='PENDING'
                  AND planned_at<=?
                ORDER BY planned_at ASC, id ASC;
                """,
                (now_text,),
            ).fetchall()
            return [ScheduledSendRow(**dict(r)) for r in rows]

    def mark_running_if_pending(self, schedule_id: int, launched_at: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE scheduled_sends
                SET status='RUNNING',
                    launched_at=?,
                    last_error=''
                WHERE id=?
                  AND status='PENDING';
                """,
                (launched_at, int(schedule_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) == 1

    def mark_done(self, schedule_id: int, finished_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_sends
                SET status='DONE',
                    finished_at=?,
                    last_error=''
                WHERE id=?;
                """,
                (finished_at, int(schedule_id)),
            )
            conn.commit()

    def mark_failed(self, schedule_id: int, finished_at: str, error_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_sends
                SET status='FAILED',
                    finished_at=?,
                    last_error=?
                WHERE id=?;
                """,
                (finished_at, str(error_text or ""), int(schedule_id)),
            )
            conn.commit()

    def cancel(self, schedule_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_sends
                SET status='CANCELED'
                WHERE id=?
                  AND status IN ('PENDING', 'FAILED');
                """,
                (int(schedule_id),),
            )
            conn.commit()
