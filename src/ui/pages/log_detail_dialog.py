# ✅ FILE: src/ui/pages/log_detail_dialog.py
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QFrame
)

from ui.pages.campaign_preview_dialog import CampaignPreviewDialog


class ClickableLabel(QLabel):
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, ev):  # type: ignore[override]
        try:
            self.doubleClicked.emit()
        except Exception:
            pass
        super().mouseDoubleClickEvent(ev)


class LogDetailDialog(QDialog):
    """
    로그(스냅샷) 상세 보기
    - 발송시간, 캠페인명, 그룹명, 수신자, 상태, 사유, 시도횟수, 메시지길이, 이미지수 등
    - 캠페인명 더블클릭 -> CampaignPreviewDialog
    """
    def __init__(
        self,
        *,
        title: str,
        detail: Dict[str, Any],
        campaigns_repo=None,
        parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "발송 상세")
        self.resize(820, 520)

        self._detail = dict(detail or {})
        self._campaigns_repo = campaigns_repo

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # header
        head = QVBoxLayout()
        head.setSpacing(4)

        self.lbl_ts = QLabel(f"발송시간: {self._detail.get('ts','')}")
        self.lbl_channel = QLabel(f"채널/그룹: {self._detail.get('channel','')}")
        self.lbl_recipient = QLabel(f"수신자: {self._detail.get('recipient','')}")
        self.lbl_status = QLabel(f"상태: {self._detail.get('status','')}  |  시도: {self._detail.get('attempt','')}")
        self.lbl_counts = QLabel(
            f"메시지길이: {self._detail.get('message_len','')}  |  이미지수: {self._detail.get('image_count','')}"
        )

        head.addWidget(self.lbl_ts)
        head.addWidget(self.lbl_channel)
        head.addWidget(self.lbl_recipient)
        head.addWidget(self.lbl_status)
        head.addWidget(self.lbl_counts)

        root.addLayout(head)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e5e7eb;")
        root.addWidget(sep)

        # campaign row (double click)
        crow = QHBoxLayout()
        crow.setSpacing(8)

        campaign_id = str(self._detail.get("campaign_id", "") or "")
        campaign_name = str(self._detail.get("campaign_name", "") or "")

        self.lbl_campaign = ClickableLabel()
        self.lbl_campaign.setText(f"캠페인: {campaign_name} (ID={campaign_id})  —  더블클릭: 캠페인 미리보기")
        self.lbl_campaign.setStyleSheet("color:#2563eb; font-weight:700;")
        self.lbl_campaign.setCursor(Qt.PointingHandCursor)
        self.lbl_campaign.doubleClicked.connect(self._open_campaign_preview)

        crow.addWidget(self.lbl_campaign, 1)
        root.addLayout(crow)

        # reason
        root.addWidget(QLabel("사유/상세"))
        self.txt_reason = QTextEdit()
        self.txt_reason.setReadOnly(True)
        self.txt_reason.setPlainText(str(self._detail.get("reason", "") or ""))
        root.addWidget(self.txt_reason, 1)

        # footer
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        root.addLayout(btns)

    def _open_campaign_preview(self) -> None:
        """
        ✅ 스냅샷 기반:
        - REPORT 모드: detail에 campaign_items가 있을 수 있음(단, image_bytes가 없을 수 있음)
        - DB(log) 모드: campaigns_repo로 캠페인 아이템 로드(가능하면)
        """
        campaign_title = str(
            self._detail.get("campaign_title", "")
            or self._detail.get("channel", "")
            or "캠페인"
        )

        def _items_need_bytes(items: list) -> bool:
            for it in items:
                # dict(리포트) 경로
                if isinstance(it, dict):
                    if str(it.get("item_type", "")).upper() != "IMAGE":
                        continue
                    b = it.get("image_bytes", None)
                    if isinstance(b, (bytes, bytearray)) and len(b) > 0:
                        continue
                    return True

                # object(DB/Repo) 경로
                typ = str(getattr(it, "item_type", "") or "").upper()
                if typ != "IMAGE":
                    continue
                b2 = getattr(it, "image_bytes", None)
                if isinstance(b2, (bytes, bytearray)) and len(b2) > 0:
                    continue
                return True

            return False

        # 1) 스냅샷 items 우선(리포트)
        items = self._detail.get("campaign_items", None)
        if isinstance(items, list) and items:
            # ✅ 스냅샷에 이미지 bytes가 없으면 DB 재조회 시도
            if _items_need_bytes(items) and self._campaigns_repo:
                try:
                    cid = int(self._detail.get("campaign_id"))
                    items_db = self._campaigns_repo.get_campaign_items(cid)
                    if items_db:
                        items = items_db
                except Exception:
                    pass

            dlg = CampaignPreviewDialog(campaign_title=campaign_title, items=items, parent=self)
            dlg.exec()
            return

        # 2) 스냅샷이 없으면 DB 재조회
        if not self._campaigns_repo:
            return

        try:
            cid = int(self._detail.get("campaign_id"))
        except Exception:
            return

        try:
            items_db = self._campaigns_repo.get_campaign_items(cid)
        except Exception:
            items_db = []

        if not items_db:
            return

        dlg = CampaignPreviewDialog(campaign_title=campaign_title, items=items_db, parent=self)
        dlg.exec()

