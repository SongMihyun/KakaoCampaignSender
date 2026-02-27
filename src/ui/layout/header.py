# src/ui/layout/header.py
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from app.version import __display_name__, __version__


class Header(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(4)

        # ✅ 좌측 타이틀: "카센더"
        self.title = QLabel(__display_name__)
        self.title.setObjectName("AppTitle")

        self.subtitle = QLabel("—")
        self.subtitle.setObjectName("SubTitle")

        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignRight)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.meta = QLabel(f"Local | {now}")
        self.meta.setObjectName("Meta")

        # ✅ Env 대신 버전 표기
        ver = __version__ if __version__ else ""
        if ver and not str(ver).startswith("v"):
            ver = f"v{ver}"
        self.ver = QLabel(ver or "v-")
        self.ver.setObjectName("Meta")

        right.addWidget(self.meta)
        right.addWidget(self.ver)

        layout.addLayout(left, 1)
        layout.addLayout(right)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)