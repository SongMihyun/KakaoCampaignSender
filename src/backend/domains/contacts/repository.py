# FILE: src/backend/domains/contacts/repository.py

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.database.schema import ensure_contacts_schema


CONTACT_SELECT_COLUMNS = """
    id,
    emp_id,
    name,
    COALESCE(customer_name, name) AS customer_name,
    COALESCE(NULLIF(TRIM(customer_honorific), ''), '고객님') AS customer_honorific,
    COALESCE(customer_position, '') AS customer_position,
    phone,
    agency,
    branch,
    COALESCE(customer_status, '') AS customer_status,
    COALESCE(tags, '') AS tags,
    COALESCE(memo2, '') AS memo2,
    last_assigned_code,
    last_assigned_label,
    last_assigned_at
"""


@dataclass
class ContactRow:
    id: int
    emp_id: str
    name: str
    customer_name: str
    customer_honorific: str
    customer_position: str
    phone: str | None
    agency: str | None
    branch: str | None
    customer_status: str = ""
    tags: str = ""
    memo2: str = ""
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None


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
            ensure_contacts_schema(conn)

            conn.execute("UPDATE contacts SET emp_id = TRIM(emp_id);")
            conn.execute("UPDATE contacts SET name = TRIM(name);")
            conn.execute("UPDATE contacts SET customer_name = TRIM(COALESCE(customer_name, name));")
            conn.execute(
                """
                UPDATE contacts
                SET customer_honorific = COALESCE(NULLIF(TRIM(customer_honorific), ''), '고객님');
                """
            )
            conn.execute("UPDATE contacts SET customer_position = TRIM(COALESCE(customer_position, ''));")
            conn.execute("UPDATE contacts SET customer_status = TRIM(COALESCE(customer_status, ''));")
            conn.execute("UPDATE contacts SET tags = TRIM(COALESCE(tags, ''));")
            conn.execute("UPDATE contacts SET memo2 = TRIM(COALESCE(memo2, ''));")
            conn.execute("UPDATE contacts SET phone = NULLIF(TRIM(phone), '');")
            conn.execute("UPDATE contacts SET agency = NULLIF(TRIM(agency), '');")
            conn.execute("UPDATE contacts SET branch = NULLIF(TRIM(branch), '');")

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

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    def _row_to_contact(self, r: sqlite3.Row) -> ContactRow:
        return ContactRow(
            id=int(r["id"]),
            emp_id=str(r["emp_id"] or ""),
            name=str(r["name"] or ""),
            customer_name=str(r["customer_name"] or r["name"] or ""),
            customer_honorific=str(r["customer_honorific"] or "고객님"),
            customer_position=str(r["customer_position"] or ""),
            phone=(str(r["phone"]) if r["phone"] is not None else None),
            agency=(str(r["agency"]) if r["agency"] is not None else None),
            branch=(str(r["branch"]) if r["branch"] is not None else None),
            customer_status=str(r["customer_status"] or ""),
            tags=str(r["tags"] or ""),
            memo2=str(r["memo2"] or ""),
            last_assigned_code=(
                str(r["last_assigned_code"]) if r["last_assigned_code"] is not None else None
            ),
            last_assigned_label=(
                str(r["last_assigned_label"]) if r["last_assigned_label"] is not None else None
            ),
            last_assigned_at=(
                str(r["last_assigned_at"]) if r["last_assigned_at"] is not None else None
            ),
        )

    def list_all(self) -> list[ContactRow]:
        with self._conn() as conn:
            cur = conn.execute(
                f"""
                SELECT {CONTACT_SELECT_COLUMNS}
                FROM contacts
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
        return [self._row_to_contact(r) for r in rows]

    def search_contacts(self, query: str) -> list[ContactRow]:
        q = (query or "").strip()
        like = f"%{q}%"

        with self._conn() as conn:
            if not q:
                cur = conn.execute(
                    f"""
                    SELECT {CONTACT_SELECT_COLUMNS}
                    FROM contacts
                    ORDER BY id ASC;
                    """
                )
            else:
                cur = conn.execute(
                    f"""
                    SELECT {CONTACT_SELECT_COLUMNS}
                    FROM contacts
                    WHERE COALESCE(emp_id,'') LIKE ?
                       OR name LIKE ?
                       OR COALESCE(customer_name,'') LIKE ?
                       OR COALESCE(customer_honorific,'') LIKE ?
                       OR COALESCE(customer_position,'') LIKE ?
                       OR COALESCE(phone,'') LIKE ?
                       OR COALESCE(agency,'') LIKE ?
                       OR COALESCE(branch,'') LIKE ?
                       OR COALESCE(customer_status,'') LIKE ?
                       OR COALESCE(tags,'') LIKE ?
                       OR COALESCE(memo2,'') LIKE ?
                    ORDER BY id ASC;
                    """,
                    (like, like, like, like, like, like, like, like, like, like, like),
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
        *,
        customer_name: str = "",
        customer_honorific: str = "고객님",
        customer_position: str = "",
        customer_status: str = "",
        tags: str = "",
        memo2: str = "",
    ) -> int:
        values = self._normalize_values(
            emp_id=emp_id,
            name=name,
            customer_name=customer_name,
            customer_honorific=customer_honorific,
            customer_position=customer_position,
            phone=phone,
            agency=agency,
            branch=branch,
            customer_status=customer_status,
            tags=tags,
            memo2=memo2,
        )

        if not values["name"]:
            raise ValueError("카카오톡 검색명(name)은 필수입니다.")

        try:
            with self._conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO contacts(
                        emp_id, name, customer_name, customer_honorific, customer_position,
                        phone, agency, branch, customer_status, tags, memo2
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._db_tuple(values),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            raise ValueError("사번(빈값 제외) 또는 전화번호가 이미 존재합니다.")

    def update(
        self,
        row_id: int,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
        *,
        customer_name: str = "",
        customer_honorific: str = "고객님",
        customer_position: str = "",
        customer_status: str = "",
        tags: str = "",
        memo2: str = "",
        last_assigned_code: str | None = None,
        last_assigned_label: str | None = None,
        last_assigned_at: str | None = None,
    ) -> None:
        values = self._normalize_values(
            emp_id=emp_id,
            name=name,
            customer_name=customer_name,
            customer_honorific=customer_honorific,
            customer_position=customer_position,
            phone=phone,
            agency=agency,
            branch=branch,
            customer_status=customer_status,
            tags=tags,
            memo2=memo2,
        )

        if not values["name"]:
            raise ValueError("카카오톡 검색명(name)은 필수입니다.")

        assignments = """
            emp_id=?,
            name=?,
            customer_name=?,
            customer_honorific=?,
            customer_position=?,
            phone=?,
            agency=?,
            branch=?,
            customer_status=?,
            tags=?,
            memo2=?,
            updated_at=datetime('now','localtime')
        """
        params: list[Any] = list(self._db_tuple(values))

        if last_assigned_code is not None:
            assignments += ", last_assigned_code=?"
            params.append(last_assigned_code)
        if last_assigned_label is not None:
            assignments += ", last_assigned_label=?"
            params.append(last_assigned_label)
        if last_assigned_at is not None:
            assignments += ", last_assigned_at=?"
            params.append(last_assigned_at)

        params.append(int(row_id))

        try:
            with self._conn() as conn:
                conn.execute(
                    f"""
                    UPDATE contacts
                    SET {assignments}
                    WHERE id=?
                    """,
                    tuple(params),
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
                values = self._values_from_import_row(r)
                if not values["name"]:
                    continue

                try:
                    conn.execute(
                        """
                        INSERT INTO contacts(
                            emp_id, name, customer_name, customer_honorific, customer_position,
                            phone, agency, branch, customer_status, tags, memo2
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        self._db_tuple(values),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    dup_skipped += 1

            conn.commit()

        return inserted, dup_skipped

    def get_by_id(self, contact_id: int) -> ContactRow | None:
        with self._conn() as conn:
            r = conn.execute(
                f"""
                SELECT {CONTACT_SELECT_COLUMNS}
                FROM contacts
                WHERE id = ? LIMIT 1;
                """,
                (int(contact_id),),
            ).fetchone()
            return self._row_to_contact(r) if r else None

    def get_contact_by_emp_id(self, emp_id: str) -> ContactRow | None:
        eid = (emp_id or "").strip()
        if not eid:
            return None
        with self._conn() as conn:
            r = conn.execute(
                f"""
                SELECT {CONTACT_SELECT_COLUMNS}
                FROM contacts
                WHERE TRIM(emp_id) = TRIM(?)
                  AND TRIM(emp_id) <> ''
                ORDER BY id ASC LIMIT 1;
                """,
                (eid,),
            ).fetchone()
            return self._row_to_contact(r) if r else None

    def _values_from_import_row(self, row: Any) -> dict[str, str]:
        if isinstance(row, dict):
            return self._normalize_values(
                emp_id=row.get("emp_id", ""),
                name=row.get("name", ""),
                customer_name=row.get("customer_name", ""),
                customer_honorific=row.get("customer_honorific", "고객님"),
                customer_position=row.get("customer_position", ""),
                phone=row.get("phone", ""),
                agency=row.get("agency", ""),
                branch=row.get("branch", ""),
                customer_status=row.get("customer_status", ""),
                tags=row.get("tags", ""),
                memo2=row.get("memo2", ""),
            )

        values = list(row or [])
        if len(values) >= 10:
            return self._normalize_values(
                emp_id="",
                name=values[0],
                customer_name=values[1],
                customer_honorific=values[2],
                customer_position=values[3],
                agency=values[4],
                branch=values[5],
                phone=values[6],
                customer_status=values[7],
                tags=values[8],
                memo2=values[9],
            )

        return self._normalize_values(
            emp_id=values[0] if len(values) > 0 else "",
            name=values[1] if len(values) > 1 else "",
            phone=values[2] if len(values) > 2 else "",
            agency=values[3] if len(values) > 3 else "",
            branch=values[4] if len(values) > 4 else "",
            customer_name="",
            customer_honorific="고객님",
            customer_position="",
            customer_status="",
            tags="",
            memo2="",
        )

    def _normalize_values(
        self,
        *,
        emp_id: Any,
        name: Any,
        customer_name: Any = "",
        customer_honorific: Any = "고객님",
        customer_position: Any = "",
        phone: Any = "",
        agency: Any = "",
        branch: Any = "",
        customer_status: Any = "",
        tags: Any = "",
        memo2: Any = "",
    ) -> dict[str, str]:
        name_text = self._text(name)
        return {
            "emp_id": self._text(emp_id),
            "name": name_text,
            "customer_name": self._text(customer_name) or name_text,
            "customer_honorific": self._text(customer_honorific) or "고객님",
            "customer_position": self._text(customer_position),
            "phone": self._text(phone),
            "agency": self._text(agency),
            "branch": self._text(branch),
            "customer_status": self._text(customer_status),
            "tags": self._text(tags),
            "memo2": self._text(memo2),
        }

    @staticmethod
    def _db_tuple(values: dict[str, str]) -> tuple[Any, ...]:
        phone = values["phone"] if values["phone"] else None
        agency = values["agency"] if values["agency"] else None
        branch = values["branch"] if values["branch"] else None
        return (
            values["emp_id"],
            values["name"],
            values["customer_name"],
            values["customer_honorific"],
            values["customer_position"],
            phone,
            agency,
            branch,
            values["customer_status"],
            values["tags"],
            values["memo2"],
        )
