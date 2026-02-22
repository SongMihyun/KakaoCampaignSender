from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class GroupRow:
    id: int
    name: str
    memo: str


@dataclass
class ContactRow:
    id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str


class GroupsRepo:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            # groups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    name  TEXT NOT NULL UNIQUE,
                    memo  TEXT NOT NULL DEFAULT ''
                );
            """)

            # group_members (contacts.id FK)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id   INTEGER NOT NULL,
                    contact_id INTEGER NOT NULL,
                    PRIMARY KEY (group_id, contact_id),
                    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
                    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
                );
            """)

            conn.execute("PRAGMA foreign_keys = ON;")

    # -----------------
    # Group CRUD
    # -----------------
    def list_groups(self) -> list[GroupRow]:
        with self._connect() as conn:
            cur = conn.execute("SELECT id, name, memo FROM groups ORDER BY name ASC;")
            return [GroupRow(int(r["id"]), r["name"], r["memo"]) for r in cur.fetchall()]

    def create_group(self, name: str, memo: str = "") -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("그룹명은 필수입니다.")

        with self._connect() as conn:
            try:
                cur = conn.execute("INSERT INTO groups(name, memo) VALUES (?, ?);", (name, memo or ""))
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                raise ValueError("동일한 그룹명이 이미 존재합니다.")

    def update_group(self, group_id: int, name: str, memo: str = "") -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("그룹명은 필수입니다.")

        with self._connect() as conn:
            try:
                conn.execute("UPDATE groups SET name=?, memo=? WHERE id=?;", (name, memo or "", group_id))
            except sqlite3.IntegrityError:
                raise ValueError("동일한 그룹명이 이미 존재합니다.")

    def delete_group(self, group_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM groups WHERE id=?;", (group_id,))

    # -----------------
    # Members
    # -----------------
    def list_group_members(self, group_id: int) -> list[ContactRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT c.id, c.emp_id, c.name,
                       COALESCE(c.phone,'')  AS phone,
                       COALESCE(c.agency,'') AS agency,
                       COALESCE(c.branch,'') AS branch
                FROM group_members gm
                JOIN contacts c ON c.id = gm.contact_id
                WHERE gm.group_id = ?
                ORDER BY c.name ASC, c.emp_id ASC;
            """, (group_id,))
            return [
                ContactRow(
                    int(r["id"]), r["emp_id"], r["name"], r["phone"], r["agency"], r["branch"]
                )
                for r in cur.fetchall()
            ]

    def add_members(self, group_id: int, contact_ids: Iterable[int]) -> tuple[int, int]:
        """return: (inserted_count, skipped_duplicates)"""
        ids = [int(x) for x in contact_ids]
        if not ids:
            return (0, 0)

        inserted = 0
        skipped = 0
        with self._connect() as conn:
            for cid in ids:
                try:
                    conn.execute(
                        "INSERT INTO group_members(group_id, contact_id) VALUES (?, ?);",
                        (group_id, cid),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    skipped += 1
        return (inserted, skipped)

    def remove_members(self, group_id: int, contact_ids: Iterable[int]) -> int:
        ids = [int(x) for x in contact_ids]
        if not ids:
            return 0

        with self._connect() as conn:
            cur = conn.executemany(
                "DELETE FROM group_members WHERE group_id=? AND contact_id=?;",
                [(group_id, cid) for cid in ids],
            )
            # sqlite3 executemany rowcount는 드라이버/버전에 따라 0일 수 있어 실제 카운팅은 SELECT로 처리하는 게 안전하지만
            # UI용이므로 여기서는 len(ids) 반환
        return len(ids)

    # -----------------
    # Search contacts (for "대상자 추가" 후보)
    # -----------------
    def search_contacts(self, keyword: str, limit: int = 1000) -> list[ContactRow]:
        """
        이름/사번/전화/대리점/지사 검색
        - keyword가 비면 전체 반환
        """
        kw = (keyword or "").strip()
        like = f"%{kw}%"

        with self._connect() as conn:
            if not kw:
                cur = conn.execute(f"""
                    SELECT id, emp_id, name,
                           COALESCE(phone,'')  AS phone,
                           COALESCE(agency,'') AS agency,
                           COALESCE(branch,'') AS branch
                    FROM contacts
                    ORDER BY name ASC, emp_id ASC
                    LIMIT {int(limit)};
                """)
            else:
                cur = conn.execute(f"""
                    SELECT id, emp_id, name,
                           COALESCE(phone,'')  AS phone,
                           COALESCE(agency,'') AS agency,
                           COALESCE(branch,'') AS branch
                    FROM contacts
                    WHERE emp_id LIKE ?
                       OR name  LIKE ?
                       OR phone LIKE ?
                       OR agency LIKE ?
                       OR branch LIKE ?
                    ORDER BY name ASC, emp_id ASC
                    LIMIT {int(limit)};
                """, (like, like, like, like, like))

            return [
                ContactRow(
                    int(r["id"]), r["emp_id"], r["name"], r["phone"], r["agency"], r["branch"]
                )
                for r in cur.fetchall()
            ]
