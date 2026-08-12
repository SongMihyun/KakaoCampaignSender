# ✅ FILE: src/backend/domains/contacts/repository.py

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ContactRow:
    id: int
    emp_id: str
    name: str
    phone: str | None
    agency: str | None
    branch: str | None
    title: str | None
    kakao_search_name: str | None


class ContactsRepo:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
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

            for col, ddl in {
                "title": "ALTER TABLE contacts ADD COLUMN title TEXT;",
                "kakao_search_name": "ALTER TABLE contacts ADD COLUMN kakao_search_name TEXT;",
            }.items():
                cur = conn.execute("PRAGMA table_info(contacts);")
                if col not in {str(row[1]) for row in cur.fetchall()}:
                    conn.execute(ddl)

            # ✅ 정규화: emp_id는 TRIM만(빈값 삭제/NULL 변환 금지: NOT NULL 컬럼이라)
            conn.execute("UPDATE contacts SET emp_id = TRIM(emp_id);")
            conn.execute("UPDATE contacts SET name   = TRIM(name);")
            conn.execute("UPDATE contacts SET phone  = NULLIF(TRIM(phone), '');")
            conn.execute("UPDATE contacts SET agency = NULLIF(TRIM(agency), '');")
            conn.execute("UPDATE contacts SET branch = NULLIF(TRIM(branch), '');")
            conn.execute("UPDATE contacts SET title  = NULLIF(TRIM(title), '');")
            conn.execute("UPDATE contacts SET kakao_search_name = NULLIF(TRIM(kakao_search_name), '');")

            # ✅ (중요) 기존 로직: emp_id 빈값 삭제는 이제 하면 안 됨
            # conn.execute("DELETE FROM contacts WHERE emp_id IS NULL OR TRIM(emp_id) = '';")  # 제거

            # ✅ 1) emp_id 중복 제거(단, emp_id가 빈값인 건 제외)
            conn.execute(
                """
                DELETE FROM contacts
                WHERE TRIM(emp_id) <> ''
                  AND id NOT IN (
                      SELECT MIN(id)
                      FROM contacts
                      WHERE TRIM(emp_id) <> ''
                      GROUP BY TRIM(emp_id)
                  );
                """
            )

            # ✅ 2) phone 중복 제거(NULL 제외, 최소 id만 유지)
            conn.execute(
                """
                DELETE FROM contacts
                WHERE phone IS NOT NULL
                  AND id NOT IN (
                      SELECT MIN(id)
                      FROM contacts
                      WHERE phone IS NOT NULL
                      GROUP BY phone
                  );
                """
            )

            # ✅ 3) UNIQUE 인덱스 재구성
            # - emp_id는 "빈값이 아닐 때만" UNIQUE
            # - phone은 NULL 제외 UNIQUE
            conn.execute("DROP INDEX IF EXISTS ux_contacts_emp_id;")
            conn.execute("DROP INDEX IF EXISTS ux_contacts_phone;")

            try:
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_emp_id
                    ON contacts(emp_id)
                    WHERE TRIM(emp_id) <> '';
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_phone
                    ON contacts(phone)
                    WHERE phone IS NOT NULL;
                    """
                )
            except sqlite3.IntegrityError as e:
                # 남아있는 중복 샘플 제공(디버깅)
                dup = conn.execute(
                    """
                    SELECT emp_id, COUNT(*) AS cnt
                    FROM contacts
                    WHERE TRIM(emp_id) <> ''
                    GROUP BY emp_id
                    HAVING COUNT(*) > 1
                    ORDER BY cnt DESC LIMIT 10;
                    """
                ).fetchall()
                sample = ", ".join([f"{r['emp_id']}({r['cnt']})" for r in dup])
                raise sqlite3.IntegrityError(f"UNIQUE 인덱스 생성 실패: emp_id 중복 잔존. 예: {sample}") from e

            conn.commit()

    def _row_to_contact(self, r: sqlite3.Row) -> ContactRow:
        return ContactRow(
            id=int(r["id"]),
            emp_id=str(r["emp_id"] or ""),
            name=str(r["name"] or ""),
            phone=(str(r["phone"]) if r["phone"] is not None else None),
            agency=(str(r["agency"]) if r["agency"] is not None else None),
            branch=(str(r["branch"]) if r["branch"] is not None else None),
            title=(str(r["title"]) if r["title"] is not None else None),
            kakao_search_name=(str(r["kakao_search_name"]) if r["kakao_search_name"] is not None else None),
        )

    def list_all(self) -> list[ContactRow]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT id, emp_id, name, phone, agency, branch, title, kakao_search_name FROM contacts ORDER BY id DESC"
            )
            rows = cur.fetchall()
        return [self._row_to_contact(r) for r in rows]

    def search_contacts(self, query: str) -> list[ContactRow]:
        q = (query or "").strip()
        like = f"%{q}%"

        with self._conn() as conn:
            if not q:
                cur = conn.execute(
                    """
                    SELECT id, emp_id, name, phone, agency, branch, title, kakao_search_name
                    FROM contacts
                    ORDER BY id ASC;
                    """
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, emp_id, name, phone, agency, branch, title, kakao_search_name
                    FROM contacts
                    WHERE COALESCE(emp_id,'') LIKE ?
                       OR name LIKE ?
                       OR COALESCE(phone,'') LIKE ?
                       OR COALESCE(agency,'') LIKE ?
                       OR COALESCE(branch,'') LIKE ?
                       OR COALESCE(title,'') LIKE ?
                       OR COALESCE(kakao_search_name,'') LIKE ?
                    ORDER BY id ASC;
                    """,
                    (like, like, like, like, like, like, like),
                )
            rows = cur.fetchall()

        return [self._row_to_contact(r) for r in rows]

    def insert(
        self,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
        title: str = "",
        kakao_search_name: str = "",
    ) -> int:
        emp_id = (emp_id or "").strip()      # ✅ 빈값 허용
        name = (name or "").strip()          # ✅ 이름만 필수
        phone = (phone or "").strip()
        agency = (agency or "").strip()
        branch = (branch or "").strip()
        title = (title or "").strip()
        kakao_search_name = (kakao_search_name or "").strip()

        if not name:
            raise ValueError("이름(name)은 필수입니다.")

        phone_db = phone if phone else None
        agency_db = agency if agency else None
        branch_db = branch if branch else None
        title_db = title if title else None
        kakao_search_name_db = kakao_search_name if kakao_search_name else None

        try:
            with self._conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO contacts(emp_id, name, phone, agency, branch, title, kakao_search_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (emp_id, name, phone_db, agency_db, branch_db, title_db, kakao_search_name_db),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            # emp_id(비어있지 않은 경우) 또는 phone 중복
            raise ValueError("사번(빈값 제외) 또는 전화번호가 이미 존재합니다.")

    def update(
        self,
        row_id: int,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
        title: str = "",
        kakao_search_name: str = "",
    ) -> None:
        emp_id = (emp_id or "").strip()
        name = (name or "").strip()
        phone = (phone or "").strip()
        agency = (agency or "").strip()
        branch = (branch or "").strip()
        title = (title or "").strip()
        kakao_search_name = (kakao_search_name or "").strip()

        if not name:
            raise ValueError("이름(name)은 필수입니다.")

        phone_db = phone if phone else None
        agency_db = agency if agency else None
        branch_db = branch if branch else None
        title_db = title if title else None
        kakao_search_name_db = kakao_search_name if kakao_search_name else None

        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    UPDATE contacts
                    SET emp_id=?, name=?, phone=?, agency=?, branch=?, title=?, kakao_search_name=?
                    WHERE id=?
                    """,
                    (emp_id, name, phone_db, agency_db, branch_db, title_db, kakao_search_name_db, row_id),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("사번(빈값 제외) 또는 전화번호가 이미 존재합니다.")

    def delete_many(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        with self._conn() as conn:
            conn.executemany("DELETE FROM contacts WHERE id=?", [(int(i),) for i in ids])
            conn.commit()

    def insert_many(self, rows) -> tuple[int, int]:
        inserted = 0
        dup_skipped = 0

        with self._conn() as conn:
            for r in rows:
                if isinstance(r, dict):
                    emp_id = (r.get("emp_id") or "").strip()
                    name = (r.get("name") or "").strip()
                    phone = (r.get("phone") or "").strip()
                    agency = (r.get("agency") or "").strip()
                    branch = (r.get("branch") or "").strip()
                    title = (r.get("title") or "").strip()
                    kakao_search_name = (r.get("kakao_search_name") or "").strip()
                else:
                    emp_id = str((r[0] if len(r) > 0 else "") or "").strip()
                    name = str((r[1] if len(r) > 1 else "") or "").strip()
                    phone = str((r[2] if len(r) > 2 else "") or "").strip()
                    agency = str((r[3] if len(r) > 3 else "") or "").strip()
                    branch = str((r[4] if len(r) > 4 else "") or "").strip()
                    title = str((r[5] if len(r) > 5 else "") or "").strip()
                    kakao_search_name = str((r[6] if len(r) > 6 else "") or "").strip()

                # ✅ 이름만 필수
                if not name:
                    continue

                phone_db = phone if phone else None
                agency_db = agency if agency else None
                branch_db = branch if branch else None
                title_db = title if title else None
                kakao_search_name_db = kakao_search_name if kakao_search_name else None

                try:
                    conn.execute(
                        """
                        INSERT INTO contacts(emp_id, name, phone, agency, branch, title, kakao_search_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (emp_id, name, phone_db, agency_db, branch_db, title_db, kakao_search_name_db),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    dup_skipped += 1

            conn.commit()

        return inserted, dup_skipped

    # -----------------
    # Single getters (for edit dialogs)
    # -----------------
    def get_by_id(self, contact_id: int) -> ContactRow | None:
        """
        ✅ 정석: PK(id)로 1건 로드
        """
        with self._conn() as conn:
            r = conn.execute(
                """
                SELECT id, emp_id, name, phone, agency, branch, title, kakao_search_name
                FROM contacts
                WHERE id = ? LIMIT 1;
                """,
                (int(contact_id),),
            ).fetchone()
            return self._row_to_contact(r) if r else None

    def get_contact_by_emp_id(self, emp_id: str) -> ContactRow | None:
        """
        ✅ 레거시 호환용: 기존 UI에서 호출하던 메서드
        - emp_id는 빈값이 있을 수 있으니 빈값은 None 처리
        """
        eid = (emp_id or "").strip()
        if not eid:
            return None
        with self._conn() as conn:
            r = conn.execute(
                """
                SELECT id, emp_id, name, phone, agency, branch, title, kakao_search_name
                FROM contacts
                WHERE TRIM(emp_id) = TRIM(?)
                  AND TRIM(emp_id) <> ''
                ORDER BY id ASC LIMIT 1;
                """,
                (eid,),
            ).fetchone()
            return self._row_to_contact(r) if r else None
