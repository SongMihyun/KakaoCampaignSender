# src/app/data/send_lists_repo.py
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


@dataclass
class SendListRecipientRow:
    id: int
    send_list_id: int
    contact_id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str
    sort_order: int


class SendListsRepo:
    """
    - send_lists: 발송리스트 메타(정렬용 sort_order 포함)
    - send_list_recipients: 당시 수신자 스냅샷
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
                # 기존 데이터는 id 기준으로 정렬값 부여
                conn.execute("""
                    UPDATE send_lists
                    SET sort_order = id
                    WHERE sort_order = 0;
                """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS send_list_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    send_list_id INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL,
                    emp_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    agency TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(send_list_id) REFERENCES send_lists(id) ON DELETE CASCADE
                );
            """)

            # 같은 (대상모드+그룹+캠페인) 조합은 1개 유지
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_send_lists_key
                ON send_lists(target_mode, COALESCE(group_id, -1), campaign_id);
            """)

            # ✅ 정렬 인덱스(이제 sort_order 존재)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS ix_send_lists_sort
                ON send_lists(sort_order, id);
            """)

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

    def delete_send_list(self, send_list_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM send_lists WHERE id=?;", (int(send_list_id),))

    def get_recipients(self, send_list_id: int) -> List[SendListRecipientRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, send_list_id, contact_id,
                       COALESCE(emp_id,'')   AS emp_id,
                       COALESCE(name,'')     AS name,
                       COALESCE(phone,'')    AS phone,
                       COALESCE(agency,'')   AS agency,
                       COALESCE(branch,'')   AS branch,
                       sort_order
                FROM send_list_recipients
                WHERE send_list_id=?
                ORDER BY sort_order ASC, id ASC;
            """, (int(send_list_id),))
            out: List[SendListRecipientRow] = []
            for r in cur.fetchall():
                out.append(SendListRecipientRow(
                    id=int(r["id"]),
                    send_list_id=int(r["send_list_id"]),
                    contact_id=int(r["contact_id"]),
                    emp_id=str(r["emp_id"] or ""),
                    name=str(r["name"] or ""),
                    phone=str(r["phone"] or ""),
                    agency=str(r["agency"] or ""),
                    branch=str(r["branch"] or ""),
                    sort_order=int(r["sort_order"] or 0),
                ))
            return out

    # UI alias
    def get_send_list_contacts(self, send_list_id: int) -> List[SendListRecipientRow]:
        return self.get_recipients(send_list_id)

    # -----------------
    # Order save
    # -----------------
    def update_send_list_orders(self, ordered_ids: List[int]) -> None:
        """
        UI에 표시된 순서대로 send_lists.sort_order를 1..N 재부여
        """
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
    # Upsert Create
    # -----------------
    def create_or_replace_send_list(
        self,
        target_mode: str,
        group_id: Optional[int],
        group_name: str,
        campaign_id: int,
        campaign_name: str,
        contacts_snapshot: List[dict],
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

            # 기존 키 조회
            old = conn.execute("""
                SELECT id
                FROM send_lists
                WHERE target_mode=?
                  AND COALESCE(group_id,-1)=COALESCE(?, -1)
                  AND campaign_id=?;
            """, (target_mode, key_group_id, int(campaign_id))).fetchone()

            keep_sort_order = None
            if old:
                keep_sort_order = conn.execute(
                    "SELECT sort_order FROM send_lists WHERE id=?;",
                    (int(old["id"]),)
                ).fetchone()
                keep_sort_order = int(keep_sort_order["sort_order"] or 0) if keep_sort_order else 0

                conn.execute("DELETE FROM send_lists WHERE id=?;", (int(old["id"]),))

            if not keep_sort_order:
                keep_sort_order = self._next_sort_order(conn)

            cur = conn.execute("""
                INSERT INTO send_lists(target_mode, group_id, group_name, campaign_id, campaign_name, sort_order)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (target_mode, key_group_id, group_name, int(campaign_id), campaign_name, int(keep_sort_order)))
            send_list_id = int(cur.lastrowid)

            order = 1
            for c in contacts_snapshot or []:
                if c.get("id") is None:
                    continue

                conn.execute("""
                    INSERT INTO send_list_recipients(
                        send_list_id, contact_id, emp_id, name, phone, agency, branch, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    send_list_id,
                    int(c.get("id")),
                    str(c.get("emp_id") or ""),
                    str(c.get("name") or ""),
                    str(c.get("phone") or ""),
                    str(c.get("agency") or ""),
                    str(c.get("branch") or ""),
                    int(order),
                ))
                order += 1

            return send_list_id
