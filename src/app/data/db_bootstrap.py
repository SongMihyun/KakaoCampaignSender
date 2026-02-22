from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.paths import contacts_db_path
from app.data.schema import ensure_send_logs_schema


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table});")
    cols = {row[1] for row in cur.fetchall()}  # row[1] = column name
    return column in cols


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table,),
    )
    return cur.fetchone() is not None


def _backup_broken_db(db_file: Path, reason: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_file.with_name(f"{db_file.stem}.bad-{ts}{db_file.suffix}")
    db_file.replace(backup)
    return backup


def ensure_db_initialized() -> Path:
    """
    ✅ AppData Local DB 운영
    - 폴더 없으면 생성
    - 깨진 DB는 백업 후 재생성
    - ✅ send_logs 테이블은 여기서 보장 생성 (UI 뜨기 전)
    """
    db_file = contacts_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------
    # DB 존재 시 검사
    # ---------------------------
    if db_file.exists():
        try:
            conn = sqlite3.connect(db_file)
            try:
                # 기존 contacts 스키마 체크 로직 유지
                if _table_exists(conn, "contacts") and not _has_column(conn, "contacts", "emp_id"):
                    conn.close()
                    _backup_broken_db(db_file, "missing column contacts.emp_id")
                    sqlite3.connect(db_file).close()
                    return db_file

                # ✅ send_logs 테이블 보장 생성
                ensure_send_logs_schema(conn)
                conn.commit()

            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        except Exception:
            # DB 파일 손상 시 백업 후 재생성
            try:
                _backup_broken_db(db_file, "db open failed")
            except Exception:
                pass
            sqlite3.connect(db_file).close()
            return db_file

        return db_file

    # ---------------------------
    # DB가 없으면 신규 생성
    # ---------------------------
    conn = sqlite3.connect(db_file)
    try:
        # ✅ 최초 생성 시에도 send_logs 생성
        ensure_send_logs_schema(conn)
        conn.commit()
    finally:
        conn.close()

    return db_file
