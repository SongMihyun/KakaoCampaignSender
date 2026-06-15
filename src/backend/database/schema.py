# ✅ FILE: src/backend/database/schema.py
from __future__ import annotations

import sqlite3


CONTACTS_COLUMNS: dict[str, str] = {
    "phone": "TEXT",
    "agency": "TEXT",
    "branch": "TEXT",
    "created_at": "TEXT",
    "search_name": "TEXT",
    "title": "TEXT",
    "honorific": "TEXT",
    "nickname": "TEXT",
    "company": "TEXT",
    "department": "TEXT",
    "team": "TEXT",
    "position": "TEXT",
    "birth_date": "TEXT",
    "birth_calendar_type": "TEXT",
    "birth_memo": "TEXT",
    "gender": "TEXT",
    "customer_type": "TEXT",
    "customer_status": "TEXT",
    "lead_status": "TEXT",
    "priority": "TEXT",
    "interest_products": "TEXT",
    "contract_status": "TEXT",
    "policy_memo": "TEXT",
    "renewal_date": "TEXT",
    "last_contacted_at": "TEXT",
    "next_contact_at": "TEXT",
    "followup_memo": "TEXT",
    "do_not_send": "INTEGER NOT NULL DEFAULT 0",
    "is_active": "INTEGER NOT NULL DEFAULT 1",
    "is_favorite": "INTEGER NOT NULL DEFAULT 0",
    "last_sent_at": "TEXT",
    "last_send_status": "TEXT",
    "last_campaign_name": "TEXT",
    "send_count": "INTEGER NOT NULL DEFAULT 0",
    "fail_count": "INTEGER NOT NULL DEFAULT 0",
    "kakao_room_type": "TEXT",
    "kakao_room_memo": "TEXT",
    "tags": "TEXT",
    "memo2": "TEXT",
    "custom_field_1": "TEXT",
    "custom_field_2": "TEXT",
    "custom_field_3": "TEXT",
    "custom_field_4": "TEXT",
    "custom_field_5": "TEXT",
    "extra_json": "TEXT",
    "last_assigned_code": "TEXT",
    "last_assigned_label": "TEXT",
    "last_assigned_at": "TEXT",
    "source": "TEXT",
    "external_id": "TEXT",
    "import_batch_id": "TEXT",
    "created_by": "TEXT",
    "updated_by": "TEXT",
    "registered_at": "TEXT",
    "status_changed_at": "TEXT",
    "updated_at": "TEXT",
}


def ensure_contacts_schema(conn: sqlite3.Connection) -> None:
    """
    contacts CRM extension migration.

    This function is intentionally idempotent. It runs on app startup and
    repository init so an installed update can safely migrate an existing DB
    before the next screen or send workflow touches the new fields.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            agency TEXT,
            branch TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )

    cols = _table_columns(conn, "contacts")
    for name, ddl in CONTACTS_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {name} {ddl};")
            cols.add(name)

    conn.execute(
        """
        UPDATE contacts
        SET search_name = name
        WHERE search_name IS NULL
           OR TRIM(search_name) = '';
        """
    )
    conn.execute(
        """
        UPDATE contacts
        SET registered_at = COALESCE(NULLIF(TRIM(registered_at), ''), NULLIF(TRIM(created_at), ''), datetime('now','localtime'))
        WHERE registered_at IS NULL
           OR TRIM(registered_at) = '';
        """
    )
    conn.execute(
        """
        UPDATE contacts
        SET status_changed_at = COALESCE(NULLIF(TRIM(status_changed_at), ''), NULLIF(TRIM(updated_at), ''), datetime('now','localtime'))
        WHERE status_changed_at IS NULL
           OR TRIM(status_changed_at) = '';
        """
    )
    conn.execute(
        """
        UPDATE contacts
        SET updated_at = COALESCE(NULLIF(TRIM(updated_at), ''), NULLIF(TRIM(created_at), ''), datetime('now','localtime'))
        WHERE updated_at IS NULL
           OR TRIM(updated_at) = '';
        """
    )

    for index_name, column in {
        "idx_contacts_search_name": "search_name",
        "idx_contacts_title": "title",
        "idx_contacts_company": "company",
        "idx_contacts_department": "department",
        "idx_contacts_team": "team",
        "idx_contacts_branch": "branch",
        "idx_contacts_birth_date": "birth_date",
        "idx_contacts_customer_status": "customer_status",
        "idx_contacts_lead_status": "lead_status",
        "idx_contacts_next_contact_at": "next_contact_at",
        "idx_contacts_registered_at": "registered_at",
        "idx_contacts_status_changed_at": "status_changed_at",
        "idx_contacts_do_not_send": "do_not_send",
        "idx_contacts_is_active": "is_active",
        "idx_contacts_tags": "tags",
        "idx_contacts_external_id": "external_id",
        "idx_contacts_last_assigned_at": "last_assigned_at",
    }.items():
        conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON contacts({column});")

    # Future design note:
    # Per-recipient assigned message values (codes/coupons/links) should live in
    # dedicated tables such as message_value_pools and message_value_items. These
    # last_assigned_* columns are only the latest summary on the contact row.


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table});")
    return {str(row[1]) for row in cur.fetchall()}


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
            status_code INTEGER NOT NULL DEFAULT 0,
            status_message TEXT NOT NULL DEFAULT '',
            step        TEXT NOT NULL DEFAULT '',
            reason      TEXT NOT NULL DEFAULT '',
            attempt     INTEGER NOT NULL DEFAULT 0,
            message_len INTEGER NOT NULL DEFAULT 0,
            image_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    for col, ddl in {
        "status_code": "ALTER TABLE send_logs ADD COLUMN status_code INTEGER NOT NULL DEFAULT 0;",
        "status_message": "ALTER TABLE send_logs ADD COLUMN status_message TEXT NOT NULL DEFAULT '';",
        "step": "ALTER TABLE send_logs ADD COLUMN step TEXT NOT NULL DEFAULT '';",
    }.items():
        try:
            cur = conn.execute("PRAGMA table_info(send_logs);")
            if col not in {str(row[1]) for row in cur.fetchall()}:
                conn.execute(ddl)
        except Exception:
            pass

    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_ts ON send_logs(ts);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_status ON send_logs(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_send_logs_status_code ON send_logs(status_code);")
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
