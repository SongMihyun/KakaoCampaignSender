# FILE: src/backend/database/schema.py
# ✅ FILE: src/backend/database/schema.py
from __future__ import annotations

import sqlite3


def ensure_send_logs_schema(conn: sqlite3.Connection) -> None:
    """
    send_logs 테이블/인덱스 생성 공통화
    - db_bootstrap, SendLogsRepo에서 동일 함수 사용
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS send_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime')),
            campaign_id INTEGER NOT NULL DEFAULT 0,
            batch_id    TEXT NOT NULL DEFAULT '',
            channel     TEXT NOT NULL DEFAULT '',
            recipient   TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT '',
            reason      TEXT NOT NULL DEFAULT '',
            attempt     INTEGER NOT NULL DEFAULT 0,
            message_len INTEGER NOT NULL DEFAULT 0,
            image_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_ts ON send_logs(ts);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_status ON send_logs(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_recipient ON send_logs(recipient);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_campaign_id ON send_logs(campaign_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_batch_id ON send_logs(batch_id);")


def ensure_scheduled_sends_schema(conn: sqlite3.Connection) -> None:
    """
    예약발송 메타 저장 테이블/인덱스 생성
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_sends (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            planned_at              TEXT NOT NULL,
            status                  TEXT NOT NULL DEFAULT 'PENDING',
            speed_mode              TEXT NOT NULL DEFAULT 'normal',
            send_list_snapshot_json TEXT NOT NULL DEFAULT '[]',
            task_name               TEXT NOT NULL DEFAULT '',
            task_path               TEXT NOT NULL DEFAULT '',
            launched_at             TEXT NOT NULL DEFAULT '',
            finished_at             TEXT NOT NULL DEFAULT '',
            last_error              TEXT NOT NULL DEFAULT '',
            created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime'))
        );
        """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_sends_status_planned_at "
        "ON scheduled_sends(status, planned_at);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_sends_task_name "
        "ON scheduled_sends(task_name);"
    )
