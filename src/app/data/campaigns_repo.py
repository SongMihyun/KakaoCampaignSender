# ✅ FILE: src/app/data/campaigns_repo.py


from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Literal, Tuple

ItemType = Literal["IMAGE", "TEXT"]


@dataclass
class CampaignRow:
    id: int
    name: str
    created_at: str


@dataclass
class CampaignItemRow:
    id: int
    campaign_id: int
    item_type: ItemType
    text: str
    image_name: str
    image_bytes: bytes
    sort_order: int


class CampaignsRepo:
    """
    캠페인(여러 개) + 캠페인 아이템(이미지/문구 혼합, 순서 저장)
    """
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaign_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL CHECK (item_type IN ('IMAGE','TEXT')),
                    text TEXT NOT NULL DEFAULT '',
                    image_name TEXT NOT NULL DEFAULT '',
                    image_bytes BLOB,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                );
            """)

    # -----------------
    # 캠페인 목록
    # -----------------
    def list_campaigns(self) -> List[CampaignRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, name, created_at
                FROM campaigns
                ORDER BY id DESC;
            """)
            return [CampaignRow(int(r["id"]), r["name"], r["created_at"]) for r in cur.fetchall()]

    def delete_campaign(self, campaign_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM campaigns WHERE id=?;", (int(campaign_id),))

    # -----------------
    # 단건 로드
    # -----------------
    def get_campaign_items(self, campaign_id: int) -> List[CampaignItemRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, campaign_id, item_type,
                       COALESCE(text,'') AS text,
                       COALESCE(image_name,'') AS image_name,
                       COALESCE(image_bytes, X'') AS image_bytes,
                       sort_order
                FROM campaign_items
                WHERE campaign_id=?
                ORDER BY sort_order ASC, id ASC;
            """, (int(campaign_id),))

            rows: List[CampaignItemRow] = []
            for r in cur.fetchall():
                rows.append(CampaignItemRow(
                    id=int(r["id"]),
                    campaign_id=int(r["campaign_id"]),
                    item_type=r["item_type"],
                    text=r["text"],
                    image_name=r["image_name"],
                    image_bytes=r["image_bytes"],
                    sort_order=int(r["sort_order"]),
                ))
            return rows

    # -----------------
    # 저장(새 캠페인 생성)
    # -----------------
    def create_campaign(self, name: str, items: List[Tuple[ItemType, dict]]) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("캠페인명은 필수입니다.")
        if not items:
            raise ValueError("캠페인 아이템이 없습니다. (이미지/문구를 추가하세요)")

        with self._connect() as conn:
            cur = conn.execute("INSERT INTO campaigns(name) VALUES (?);", (name,))
            cid = int(cur.lastrowid)

            order = 1
            for t, payload in items:
                if t == "TEXT":
                    text = (payload.get("text") or "").strip()
                    conn.execute("""
                        INSERT INTO campaign_items(campaign_id, item_type, text, sort_order)
                        VALUES (?, 'TEXT', ?, ?);
                    """, (cid, text, order))
                else:
                    img_name = (payload.get("image_name") or "").strip()
                    img_bytes = payload.get("image_bytes") or b""
                    if not img_bytes:
                        order += 1
                        continue

                    conn.execute("""
                        INSERT INTO campaign_items(campaign_id, item_type, image_name, image_bytes, sort_order)
                        VALUES (?, 'IMAGE', ?, ?, ?);
                    """, (cid, img_name, img_bytes, order))
                order += 1

            return cid

