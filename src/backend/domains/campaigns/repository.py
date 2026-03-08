# ✅ FILE: src/backend/domains/campaigns/repository.py
from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from io import BytesIO
from typing import List, Literal, Tuple

from PIL import Image

from app.paths import user_data_dir

ItemType = Literal["IMAGE", "TEXT"]
SendMode = Literal["clipboard", "multi_attach"]


@dataclass
class CampaignRow:
    id: int
    name: str
    created_at: str
    send_mode: str


@dataclass
class CampaignItemRow:
    id: int
    campaign_id: int
    item_type: ItemType
    text: str
    image_name: str
    image_bytes: bytes
    image_path: str
    sort_order: int


class CampaignsRepo:
    """
    캠페인(여러 개) + 캠페인 아이템(이미지/문구 혼합, 순서 저장)
    이미지 파일은 앱 전용 asset 경로에도 저장한다.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        cur = conn.execute(f"PRAGMA table_info({table});")
        rows = cur.fetchall()
        for r in rows:
            if str(r["name"]).strip().lower() == column.strip().lower():
                return True
        return False

    def _campaign_assets_root(self) -> str:
        root = os.path.join(user_data_dir(), "campaign_assets")
        os.makedirs(root, exist_ok=True)
        return root

    def _campaign_assets_dir(self, campaign_id: int) -> str:
        path = os.path.join(self._campaign_assets_root(), f"campaign_{int(campaign_id)}")
        os.makedirs(path, exist_ok=True)
        return path

    def _normalize_ext_from_bytes(self, image_bytes: bytes, default_ext: str = ".png") -> str:
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                fmt = str(getattr(img, "format", "") or "").upper()
                if fmt == "JPEG":
                    return ".jpg"
                if fmt == "PNG":
                    return ".png"
                if fmt == "WEBP":
                    return ".webp"
        except Exception:
            pass
        return default_ext

    def _write_campaign_asset(
        self,
        *,
        campaign_id: int,
        order: int,
        image_bytes: bytes,
    ) -> str:
        assets_dir = self._campaign_assets_dir(campaign_id)
        ext = self._normalize_ext_from_bytes(image_bytes, default_ext=".png")
        file_name = f"img{int(order):03d}{ext}"
        path = os.path.join(assets_dir, file_name)

        with open(path, "wb") as f:
            f.write(image_bytes)

        return path

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    send_mode TEXT NOT NULL DEFAULT 'clipboard',
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
                    image_path TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                );
            """)

            # migration: campaigns.send_mode
            if not self._column_exists(conn, "campaigns", "send_mode"):
                conn.execute("""
                    ALTER TABLE campaigns
                    ADD COLUMN send_mode TEXT NOT NULL DEFAULT 'clipboard';
                """)

            # migration: campaign_items.image_path
            if not self._column_exists(conn, "campaign_items", "image_path"):
                conn.execute("""
                    ALTER TABLE campaign_items
                    ADD COLUMN image_path TEXT NOT NULL DEFAULT '';
                """)

            conn.execute("""
                UPDATE campaigns
                SET send_mode = 'clipboard'
                WHERE send_mode IS NULL
                   OR TRIM(send_mode) = ''
                   OR send_mode NOT IN ('clipboard', 'multi_attach');
            """)

            conn.execute("""
                UPDATE campaign_items
                SET image_path = ''
                WHERE image_path IS NULL;
            """)

    # -----------------
    # 캠페인 목록
    # -----------------
    def list_campaigns(self) -> List[CampaignRow]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, name, created_at, COALESCE(send_mode, 'clipboard') AS send_mode
                FROM campaigns
                ORDER BY id DESC;
            """)
            return [
                CampaignRow(
                    id=int(r["id"]),
                    name=r["name"],
                    created_at=r["created_at"],
                    send_mode=str(r["send_mode"] or "clipboard"),
                )
                for r in cur.fetchall()
            ]

    def get_campaign(self, campaign_id: int) -> CampaignRow | None:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT id, name, created_at, COALESCE(send_mode, 'clipboard') AS send_mode
                FROM campaigns
                WHERE id = ?;
            """, (int(campaign_id),))
            r = cur.fetchone()
            if not r:
                return None

            return CampaignRow(
                id=int(r["id"]),
                name=r["name"],
                created_at=r["created_at"],
                send_mode=str(r["send_mode"] or "clipboard"),
            )

    def delete_campaign(self, campaign_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM campaigns WHERE id=?;", (int(campaign_id),))

        # asset 폴더 정리
        try:
            shutil.rmtree(self._campaign_assets_dir(int(campaign_id)), ignore_errors=True)
        except Exception:
            pass

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
                       COALESCE(image_path, '') AS image_path,
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
                    image_path=str(r["image_path"] or ""),
                    sort_order=int(r["sort_order"]),
                ))
            return rows

    # -----------------
    # 저장(새 캠페인 생성)
    # -----------------
    def create_campaign(
        self,
        name: str,
        items: List[Tuple[ItemType, dict]],
        send_mode: SendMode = "clipboard",
    ) -> int:
        name = (name or "").strip()
        send_mode = (send_mode or "clipboard").strip().lower()

        if send_mode not in ("clipboard", "multi_attach"):
            send_mode = "clipboard"

        if not name:
            raise ValueError("캠페인명은 필수입니다.")
        if not items:
            raise ValueError("캠페인 아이템이 없습니다. (이미지/문구를 추가하세요)")

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO campaigns(name, send_mode) VALUES (?, ?);",
                (name, send_mode),
            )
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

                    image_path = self._write_campaign_asset(
                        campaign_id=cid,
                        order=order,
                        image_bytes=img_bytes,
                    )

                    conn.execute("""
                        INSERT INTO campaign_items(
                            campaign_id, item_type, image_name, image_bytes, image_path, sort_order
                        )
                        VALUES (?, 'IMAGE', ?, ?, ?, ?);
                    """, (cid, img_name, img_bytes, image_path, order))
                order += 1

            return cid