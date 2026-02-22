from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QFrame, QPushButton, QHBoxLayout
)

# campaigns_repo.py의 CampaignItemRow 형태(필드명만 맞으면 됨)
# item_type: "IMAGE" | "TEXT"
# text, image_name, image_bytes, sort_order


class CampaignPreviewDialog(QDialog):
    """
    캠페인 아이템(IMAGE/TEXT)을 순서대로 미리보기 팝업으로 보여줌
    """

    def __init__(self, campaign_title: str, items: Sequence, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"캠페인 미리보기 - {campaign_title}")
        self.resize(780, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        hdr = QLabel(f"캠페인: {campaign_title}")
        hdr.setStyleSheet("font-size:16px; font-weight:800;")
        root.addWidget(hdr)

        desc = QLabel("이미지/문구가 저장된 순서대로 표시됩니다.")
        desc.setStyleSheet("color:#6b7280;")
        root.addWidget(desc)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)

        bv = QVBoxLayout(body)
        bv.setContentsMargins(10, 10, 10, 10)
        bv.setSpacing(10)

        if not items:
            empty = QLabel("(캠페인 아이템이 없습니다.)")
            empty.setStyleSheet("color:#6b7280;")
            bv.addWidget(empty)
        else:
            for idx, it in enumerate(items, start=1):
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background:#ffffff;
                        border:1px solid #e5e7eb;
                        border-radius:12px;
                    }
                """)
                cv = QVBoxLayout(card)
                cv.setContentsMargins(12, 12, 12, 12)
                cv.setSpacing(8)

                # 헤더 라인
                if getattr(it, "item_type", "") == "TEXT":
                    tag = QLabel(f"{idx}. 문구")
                    tag.setStyleSheet("font-weight:700;")
                    cv.addWidget(tag)

                    txt = QLabel(getattr(it, "text", "") or "(빈 문구)")
                    txt.setWordWrap(True)
                    txt.setStyleSheet("font-size:13px;")
                    cv.addWidget(txt)

                else:  # IMAGE
                    name = getattr(it, "image_name", "") or "(이미지)"
                    tag = QLabel(f"{idx}. 이미지 - {name}")
                    tag.setStyleSheet("font-weight:700;")
                    cv.addWidget(tag)

                    img_label = QLabel()
                    img_label.setAlignment(Qt.AlignCenter)
                    img_label.setMinimumHeight(240)
                    img_label.setStyleSheet("""
                        QLabel {
                            background:#f9fafb;
                            border:1px dashed #d1d5db;
                            border-radius:12px;
                        }
                    """)
                    cv.addWidget(img_label)

                    data = getattr(it, "image_bytes", b"") or b""
                    pix = QPixmap()
                    if data and pix.loadFromData(data):
                        # 가로폭 기준으로 보기 좋게 스케일
                        target_w = 680
                        scaled = pix.scaledToWidth(target_w, Qt.SmoothTransformation)
                        img_label.setPixmap(scaled)
                        img_label.setText("")
                    else:
                        img_label.setText("이미지를 불러올 수 없습니다.")

                bv.addWidget(card)

            bv.addStretch(1)

        # 하단 닫기 버튼
        btns = QHBoxLayout()
        btns.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        root.addLayout(btns)
