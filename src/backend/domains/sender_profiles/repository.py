from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.database.schema import ensure_sender_profiles_schema
from backend.domains.sender_profiles.models import SenderProfile


class SenderProfilesRepo:
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
            ensure_sender_profiles_schema(conn)
            conn.commit()

    def get_default(self) -> SenderProfile:
        with self._conn() as conn:
            ensure_sender_profiles_schema(conn)
            row = conn.execute(
                """
                SELECT id, profile_name, sender_name, sender_position, sender_company,
                       sender_branch, sender_phone, default_signature, is_default,
                       is_active, created_at, updated_at
                FROM sender_profiles
                WHERE is_default = 1
                  AND is_active = 1
                ORDER BY id ASC
                LIMIT 1;
                """
            ).fetchone()
            conn.commit()

        if row is None:
            return SenderProfile()
        return self._row_to_model(row)

    def save_default(self, profile: SenderProfile) -> int:
        profile_name = (profile.profile_name or "기본 발신자").strip() or "기본 발신자"
        sender_name = (profile.sender_name or "").strip()
        sender_position = (profile.sender_position or "").strip()
        sender_company = (profile.sender_company or "").strip()
        sender_branch = (profile.sender_branch or "").strip()
        sender_phone = (profile.sender_phone or "").strip()
        default_signature = (profile.default_signature or "").strip()

        with self._conn() as conn:
            ensure_sender_profiles_schema(conn)
            current = conn.execute(
                """
                SELECT id
                FROM sender_profiles
                WHERE is_default = 1
                  AND is_active = 1
                ORDER BY id ASC
                LIMIT 1;
                """
            ).fetchone()

            if current is None:
                cur = conn.execute(
                    """
                    INSERT INTO sender_profiles (
                        profile_name, sender_name, sender_position, sender_company,
                        sender_branch, sender_phone, default_signature, is_default, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1);
                    """,
                    (
                        profile_name,
                        sender_name,
                        sender_position,
                        sender_company,
                        sender_branch,
                        sender_phone,
                        default_signature,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)

            profile_id = int(current["id"])
            conn.execute(
                """
                UPDATE sender_profiles
                SET profile_name = ?,
                    sender_name = ?,
                    sender_position = ?,
                    sender_company = ?,
                    sender_branch = ?,
                    sender_phone = ?,
                    default_signature = ?,
                    is_default = 1,
                    is_active = 1,
                    updated_at = datetime('now','localtime')
                WHERE id = ?;
                """,
                (
                    profile_name,
                    sender_name,
                    sender_position,
                    sender_company,
                    sender_branch,
                    sender_phone,
                    default_signature,
                    profile_id,
                ),
            )
            conn.commit()
            return profile_id

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> SenderProfile:
        return SenderProfile(
            id=int(row["id"] or 0),
            profile_name=str(row["profile_name"] or "기본 발신자"),
            sender_name=str(row["sender_name"] or ""),
            sender_position=str(row["sender_position"] or ""),
            sender_company=str(row["sender_company"] or ""),
            sender_branch=str(row["sender_branch"] or ""),
            sender_phone=str(row["sender_phone"] or ""),
            default_signature=str(row["default_signature"] or ""),
            is_default=int(row["is_default"] or 0),
            is_active=int(row["is_active"] or 0),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
