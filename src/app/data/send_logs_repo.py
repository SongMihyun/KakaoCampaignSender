# src/app/data/send_logs_repo.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional, List
from app.data.schema import ensure_send_logs_schema


@dataclass
class SendLogRow:
    id: int
    ts: str
    campaign_id: int
    batch_id: str
    channel: str
    recipient: str
    status: str
    reason: str
    attempt: int
    message_len: int
    image_count: int


class SendLogsRepo:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # ✅ 생성자에서도 한번 보장(설치 직후/첫 실행 안정성)
        try:
            self.ensure_tables()
        except Exception:
            # 부팅 단계에서 db_bootstrap이 만들기도 하므로 여기서는 조용히 무시
            pass

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass
        return con

    # ✅ 핵심: 테이블이 없으면 자동 생성
    def ensure_tables(self) -> None:
        with self._conn() as con:
            ensure_send_logs_schema(con)
            con.commit()

    def list_logs(
        self,
        status: Optional[str] = None,
        keyword: str = "",
        limit: int = 2000,
        offset: int = 0,
    ) -> List[SendLogRow]:
        # ✅ 호출 시마다 보장(설치/업데이트/DB 깨짐 대응)
        self.ensure_tables()

        kw = (keyword or "").strip()
        where = []
        params = []

        if status:
            where.append("status = ?")
            params.append(status)

        if kw:
            where.append("(recipient LIKE ? OR reason LIKE ? OR channel LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
            SELECT id, ts, campaign_id, batch_id, channel, recipient, status, reason, attempt, message_len, image_count
            FROM send_logs
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([int(limit), int(offset)])

        with self._conn() as con:
            cur = con.execute(sql, params)
            rows = cur.fetchall()

        return [
            SendLogRow(
                id=int(r["id"]),
                ts=str(r["ts"]),
                campaign_id=int(r["campaign_id"]),
                batch_id=str(r["batch_id"] or ""),
                channel=str(r["channel"] or ""),
                recipient=str(r["recipient"] or ""),
                status=str(r["status"] or ""),
                reason=str(r["reason"] or ""),
                attempt=int(r["attempt"]),
                message_len=int(r["message_len"]),
                image_count=int(r["image_count"]),
            )
            for r in rows
        ]

    def add_log(
        self,
        *,
        campaign_id: int = 0,
        batch_id: str = "",
        channel: str = "",
        recipient: str = "",
        status: str = "",
        reason: str = "",
        attempt: int = 0,
        message_len: int = 0,
        image_count: int = 0,
    ) -> int:
        """
        (선택) 로그 저장용 API. 기존 코드가 con.execute로 직접 넣고 있다면 없어도 되지만,
        앞으로 표준화하려면 이걸 쓰는 게 좋습니다.
        """
        self.ensure_tables()
        with self._conn() as con:
            cur = con.execute(
                """
                INSERT INTO send_logs(
                    campaign_id, batch_id, channel, recipient, status, reason, attempt, message_len, image_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(campaign_id),
                    str(batch_id or ""),
                    str(channel or ""),
                    str(recipient or ""),
                    str(status or ""),
                    str(reason or ""),
                    int(attempt),
                    int(message_len),
                    int(image_count),
                ),
            )
            con.commit()
            return int(cur.lastrowid or 0)

    def reset_all(self) -> None:
        """
        ✅ send_logs만 초기화한다.
        다른 테이블/파일/로컬데이터는 절대 삭제하지 않는다.
        """
        self.ensure_tables()
        with self._conn() as con:
            con.execute("DELETE FROM send_logs;")
            # sqlite autoincrement 초기화(테이블이 AUTOINCREMENT일 때만 의미 있음)
            try:
                con.execute("DELETE FROM sqlite_sequence WHERE name='send_logs';")
            except Exception:
                pass
            con.commit()

    def get_retry_targets(self) -> List[str]:
        self.ensure_tables()
        with self._conn() as con:
            cur = con.execute(
                """
                SELECT recipient, reason
                FROM send_logs
                WHERE status = 'FAIL'
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
        return [f"{r['recipient']} | {r['reason']}" for r in rows]
