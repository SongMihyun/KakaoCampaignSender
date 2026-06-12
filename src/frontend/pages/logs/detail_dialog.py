# FILE: src/frontend/pages/logs/detail_dialog.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QFrame,
)

from frontend.pages.campaigns.preview_dialog import CampaignPreviewDialog
from backend.core.status_codes import detail_text


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

    표시 항목:
    - 발송시간, 캠페인명, 그룹명, 수신자, 상태, 사유, 시도횟수, 메시지길이, 이미지수 등
    - 캠페인명 더블클릭 -> CampaignPreviewDialog

    구조 원칙:
    - UI는 CampaignsRepo를 직접 알지 않는다.
    - 캠페인 재조회는 CampaignsService를 통해 수행한다.
    """

    def __init__(
        self,
        *,
        title: str,
        detail: Dict[str, Any],
        campaigns_service=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "발송 상세")
        self.resize(820, 520)

        self._detail = dict(detail or {})
        self._campaigns_service = campaigns_service

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        head = QVBoxLayout()
        head.setSpacing(4)

        self.lbl_ts = QLabel(f"발송시간: {self._detail.get('ts', '')}")
        self.lbl_channel = QLabel(f"채널/그룹: {self._detail.get('channel', '')}")
        self.lbl_recipient = QLabel(f"수신자: {self._detail.get('recipient', '')}")
        self.lbl_status = QLabel(
            f"상태: {self._detail.get('status', '')}  |  코드: {self._detail.get('status_code', '')}  |  시도: {self._detail.get('attempt', '')}"
        )
        self.lbl_step = QLabel(f"STEP: {self._detail.get('step', '')}  |  메시지: {self._detail.get('status_message', '')}")
        self.lbl_counts = QLabel(
            f"메시지길이: {self._detail.get('message_len', '')}  |  이미지수: {self._detail.get('image_count', '')}"
        )

        head.addWidget(self.lbl_ts)
        head.addWidget(self.lbl_channel)
        head.addWidget(self.lbl_recipient)
        head.addWidget(self.lbl_status)
        head.addWidget(self.lbl_step)
        head.addWidget(self.lbl_counts)

        root.addLayout(head)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e5e7eb;")
        root.addWidget(sep)

        crow = QHBoxLayout()
        crow.setSpacing(8)

        campaign_id = str(self._detail.get("campaign_id", "") or "")
        campaign_name = str(self._detail.get("campaign_name", "") or "")

        self.lbl_campaign = ClickableLabel()
        self.lbl_campaign.setText(
            f"캠페인: {campaign_name} (ID={campaign_id})  —  더블클릭: 캠페인 미리보기"
        )
        self.lbl_campaign.setStyleSheet("color:#2563eb; font-weight:700;")
        self.lbl_campaign.setCursor(Qt.PointingHandCursor)
        self.lbl_campaign.doubleClicked.connect(self._open_campaign_preview)

        crow.addWidget(self.lbl_campaign, 1)
        root.addLayout(crow)

        root.addWidget(QLabel("사유/상세"))

        self.txt_reason = QTextEdit()
        self.txt_reason.setReadOnly(True)
        self.txt_reason.setPlainText(self._build_reason_text())
        root.addWidget(self.txt_reason, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)

        close = QPushButton("닫기")
        btn_code = QPushButton("오류코드 설명")
        btn_code.clicked.connect(self._show_status_detail)
        btns.addWidget(btn_code)
        close.clicked.connect(self.accept)
        btns.addWidget(close)

        root.addLayout(btns)

    def _show_status_detail(self) -> None:
        try:
            code = int(self._detail.get("status_code") or 0)
        except Exception:
            code = 0
        if not code:
            code = 9000
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(self, "오류코드 상세 설명", detail_text(code))

    def _build_reason_text(self) -> str:
        lines = [str(self._detail.get("reason", "") or "").strip()]
        last_success = str(self._detail.get("last_success_step", "") or "").strip()
        failure_step = str(self._detail.get("failure_step", "") or "").strip()
        retryable = self._detail.get("retryable", "")
        if last_success:
            lines += ["", f"마지막 성공 단계: {last_success}"]
        if failure_step:
            lines.append(f"실패 단계: {failure_step}")
        if retryable != "":
            lines.append(f"재시도 가능: {'예' if bool(retryable) else '아니오'}")

        steps = self._detail.get("debug_steps", [])
        if isinstance(steps, list) and steps:
            lines += ["", "[debug_steps]"]
            for step in steps:
                if not isinstance(step, dict):
                    continue
                name = str(step.get("step", "") or "")
                ok = "OK" if bool(step.get("ok")) else "FAIL"
                at = str(step.get("at", "") or "")
                detail = str(step.get("detail", "") or "")
                line = f"- {name} | {ok}"
                if at:
                    line += f" | {at}"
                if detail:
                    line += f" | {detail}"
                extra = step.get("extra", None)
                if extra:
                    try:
                        line += " | extra=" + json.dumps(extra, ensure_ascii=False)
                    except Exception:
                        line += f" | extra={extra}"
                lines.append(line)

        return "\n".join([line for line in lines if line is not None]).strip()

    def _open_campaign_preview(self) -> None:
        """
        스냅샷 기반 우선:
        1) detail.campaign_items 사용
        2) 단, 이미지 bytes가 없으면 CampaignsService로 DB 재조회 시도
        3) 스냅샷 자체가 없으면 CampaignsService로 DB 재조회
        """
        campaign_title = str(
            self._detail.get("campaign_title", "")
            or self._detail.get("channel", "")
            or "캠페인"
        )

        items = self._detail.get("campaign_items", None)
        if isinstance(items, list) and items:
            if self._items_need_bytes(items):
                items_db = self._load_campaign_items_from_service()
                if items_db:
                    items = items_db

            dlg = CampaignPreviewDialog(
                campaign_title=campaign_title,
                items=items,
                parent=self,
            )
            dlg.exec()
            return

        items_db = self._load_campaign_items_from_service()
        if not items_db:
            return

        dlg = CampaignPreviewDialog(
            campaign_title=campaign_title,
            items=items_db,
            parent=self,
        )
        dlg.exec()

    def _load_campaign_items_from_service(self) -> list:
        if not self._campaigns_service:
            return []

        try:
            campaign_id = int(self._detail.get("campaign_id"))
        except Exception:
            return []

        try:
            items = self._campaigns_service.get_campaign_items(campaign_id)
        except Exception:
            return []

        return items or []

    def _items_need_bytes(self, items: list) -> bool:
        for item in items:
            if isinstance(item, dict):
                if str(item.get("item_type", "")).upper() != "IMAGE":
                    continue

                image_bytes = item.get("image_bytes", None)
                if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
                    continue
                return True

            item_type = str(getattr(item, "item_type", "") or "").upper()
            if item_type != "IMAGE":
                continue

            image_bytes = getattr(item, "image_bytes", None)
            if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
                continue
            return True

        return False
