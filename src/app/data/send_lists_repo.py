# ✅ FILE: src/app/data/send_lists_repo.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SendListRow:
    id: int
    target_mode: str          # "ALL" | "GROUP"
    group_id: Optional[int]
    group_name: str
    campaign_id: int
    campaign_name: str
    sort_order: int
    created_at: str


class SendListsRepo:
    """
    ✅ 참조형 설계
    - send_lists: 발송리스트 메타만 저장(필터/캠페인/정렬)
    - recipients는 저장하지 않음(항상 최신 contacts/groups 조회)
    """
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_has_column(self, conn: sqlite3.Connection, table: str, col: str) -> bool:
        cur = conn.execute(f"PRAGMA table_info({table});")
        cols = [r["name"] for r in cur.fetchall()]
        return col in cols

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS send_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_mode TEXT NOT NULL CHECK (target_mode IN ('ALL','GROUP')),
                    group_id INTEGER,
                    group_name TEXT NOT NULL DEFAULT '',
                    campaign_id INTEGER NOT NULL,
                    campaign_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)

            # ✅ 마이그레이션: sort_order 컬럼이 없으면 추가
            if not self._table_has_column(conn, "send_lists", "sort_order"):
                conn.execute("ALTER TABLE send_lists ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;")
                conn.execute("""
                    UPDATE send_lists
                    SET sort_order = id
                    WHERE sort_order = 0;
                """)

            # ✅ 같은 (대상모드+그룹+캠페인) 조합은 1개 유지
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_send_lists_key
                ON send_lists(target_mode, COALESCE(group_id, -1), campaign_id);
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_send_lists_sort
                ON send_lists(sort_order, id);
            """)

            # ✅ (선택) 레거시 테이블 제거: 참조형 전환 완료 후에만 적용
            try:
                conn.execute("DROP TABLE IF EXISTS send_list_recipients;")
            except Exception:
                pass


    def _next_sort_order(self, conn: sqlite3.Connection) -> int:
        r = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM send_lists;").fetchone()
        return int(r["m"] or 0) + 1

    # -----------------
    # Lists
    # -----------------
    def list_send_lists(self) -> List[SendListRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, target_mode,
                       group_id,
                       COALESCE(group_name,'') AS group_name,
                       campaign_id,
                       COALESCE(campaign_name,'') AS campaign_name,
                       COALESCE(sort_order, 0) AS sort_order,
                       created_at
                FROM send_lists
                ORDER BY sort_order ASC, id ASC;
            """)
            out: List[SendListRow] = []
            for r in cur.fetchall():
                out.append(SendListRow(
                    id=int(r["id"]),
                    target_mode=str(r["target_mode"] or ""),
                    group_id=(int(r["group_id"]) if r["group_id"] is not None else None),
                    group_name=str(r["group_name"] or ""),
                    campaign_id=int(r["campaign_id"]),
                    campaign_name=str(r["campaign_name"] or ""),
                    sort_order=int(r["sort_order"] or 0),
                    created_at=str(r["created_at"] or ""),
                ))
            return out

    def get_send_list_meta(self, send_list_id: int) -> Optional[SendListRow]:
        with self._connect() as conn:
            r = conn.execute("""
                SELECT id, target_mode,
                       group_id,
                       COALESCE(group_name,'') AS group_name,
                       campaign_id,
                       COALESCE(campaign_name,'') AS campaign_name,
                       COALESCE(sort_order, 0) AS sort_order,
                       created_at
                FROM send_lists
                WHERE id=?;
            """, (int(send_list_id),)).fetchone()
            if not r:
                return None
            return SendListRow(
                id=int(r["id"]),
                target_mode=str(r["target_mode"] or ""),
                group_id=(int(r["group_id"]) if r["group_id"] is not None else None),
                group_name=str(r["group_name"] or ""),
                campaign_id=int(r["campaign_id"]),
                campaign_name=str(r["campaign_name"] or ""),
                sort_order=int(r["sort_order"] or 0),
                created_at=str(r["created_at"] or ""),
            )

    def delete_send_list(self, send_list_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM send_lists WHERE id=?;", (int(send_list_id),))

    # -----------------
    # Order save
    # -----------------
    def update_send_list_orders(self, ordered_ids: List[int]) -> None:
        if not ordered_ids:
            return
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            for idx, sid in enumerate(ordered_ids, start=1):
                conn.execute(
                    "UPDATE send_lists SET sort_order=? WHERE id=?;",
                    (int(idx), int(sid)),
                )

    # -----------------
    # Upsert Create (✅ 참조형: recipients 저장 없음)
    # -----------------
    def create_or_replace_send_list(
        self,
        target_mode: str,
        group_id: Optional[int],
        group_name: str,
        campaign_id: int,
        campaign_name: str,
    ) -> int:
        target_mode = (target_mode or "").strip().upper()
        if target_mode not in ("ALL", "GROUP"):
            raise ValueError("target_mode는 ALL/GROUP만 허용됩니다.")
        if campaign_id is None:
            raise ValueError("campaign_id는 필수입니다.")

        key_group_id = group_id if target_mode == "GROUP" else None

        group_name = (group_name or "").strip()
        campaign_name = (campaign_name or "").strip()

        if target_mode == "ALL" and not group_name:
            group_name = "전체"
        if target_mode == "GROUP" and not group_name:
            group_name = f"그룹({key_group_id})"
        if not campaign_name:
            campaign_name = f"캠페인({int(campaign_id)})"

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            old = conn.execute("""
                SELECT id
                FROM send_lists
                WHERE target_mode=?
                  AND COALESCE(group_id,-1)=COALESCE(?, -1)
                  AND campaign_id=?;
            """, (target_mode, key_group_id, int(campaign_id))).fetchone()

            keep_sort_order = None
            if old:
                rso = conn.execute(
                    "SELECT sort_order FROM send_lists WHERE id=?;",
                    (int(old["id"]),)
                ).fetchone()
                keep_sort_order = int(rso["sort_order"] or 0) if rso else 0
                conn.execute("DELETE FROM send_lists WHERE id=?;", (int(old["id"]),))

            if not keep_sort_order:
                keep_sort_order = self._next_sort_order(conn)

            cur = conn.execute("""
                INSERT INTO send_lists(target_mode, group_id, group_name, campaign_id, campaign_name, sort_order)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (
                target_mode,
                key_group_id,
                group_name,
                int(campaign_id),
                campaign_name,
                int(keep_sort_order),
            ))
            return int(cur.lastrowid)