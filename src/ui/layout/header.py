from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu

from app.version import __version__


class Header(QWidget):
    # ✅ MainWindow가 받아서 처리할 시그널
    logout_requested = Signal()
    uninstall_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # -------------------
        # Left
        # -------------------
        left = QVBoxLayout()
        left.setSpacing(4)

        self.title = QLabel("Campaign Sender")
        self.title.setObjectName("AppTitle")

        self.subtitle = QLabel("—")
        self.subtitle.setObjectName("SubTitle")

        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        # -------------------
        # Right
        # -------------------
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignRight)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.meta = QLabel(f"Local | {now}")
        self.meta.setObjectName("Meta")

        # ✅ Env 대신 버전 표시
        v = (__version__ or "").strip()
        if not v or v == "__VERSION__":
            v = "dev"
        self.version = QLabel(f"Version: {v}")
        self.version.setObjectName("Meta")

        # ✅ 버전 옆 햄버거 + 메뉴
        menu_row = QHBoxLayout()
        menu_row.setSpacing(8)
        menu_row.setAlignment(Qt.AlignRight)

        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(34, 28)
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.setToolTip("메뉴")
        # 버튼이 너무 밋밋하면 아래 라인 유지
        self.btn_menu.setStyleSheet(
            "QPushButton { border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff; }"
            "QPushButton:hover { background: #f3f4f6; }"
        )

        self._menu = QMenu(self)

        act_logout = QAction("로그아웃", self)
        act_uninstall = QAction("프로그램 제거", self)

        self._menu.addAction(act_logout)
        self._menu.addSeparator()
        self._menu.addAction(act_uninstall)

        act_logout.triggered.connect(self.logout_requested.emit)
        act_uninstall.triggered.connect(self.uninstall_requested.emit)

        self.btn_menu.clicked.connect(self._open_menu)

        menu_row.addWidget(self.version)
        menu_row.addWidget(self.btn_menu)

        right.addWidget(self.meta)
        right.addLayout(menu_row)

        layout.addLayout(left, 1)
        layout.addLayout(right)

    def _open_menu(self) -> None:
        # 버튼 바로 아래에 메뉴 띄우기
        try:
            pos = self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomRight())
            self._menu.exec(pos)
        except Exception:
            pass

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)