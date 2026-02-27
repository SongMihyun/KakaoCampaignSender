# src/ui/layout/header.py
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QToolButton, QMenu, QGridLayout, QSizePolicy
)

from app.version import __display_name__, __version__


class Header(QWidget):
    logout_requested = Signal()
    uninstall_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # -----------------
        # Left
        # -----------------
        left = QVBoxLayout()
        left.setSpacing(4)

        self.title = QLabel(__display_name__)
        self.title.setObjectName("AppTitle")

        self.subtitle = QLabel("—")
        self.subtitle.setObjectName("SubTitle")

        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        # -----------------
        # Right (grid to avoid overlap)
        # -----------------
        right_wrap = QWidget()
        right_grid = QGridLayout(right_wrap)
        right_grid.setContentsMargins(0, 0, 0, 0)
        right_grid.setHorizontalSpacing(8)
        right_grid.setVerticalSpacing(4)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.meta = QLabel(f"Local | {now}")
        self.meta.setObjectName("Meta")
        self.meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.meta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        ver = __version__ if __version__ else ""
        if ver and not str(ver).startswith("v"):
            ver = f"v{ver}"
        self.ver = QLabel(ver or "v-")
        self.ver.setObjectName("Meta")
        self.ver.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ver.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ✅ Hamburger button (fixed size, no layout jumping)
        self.btn_menu = QToolButton()
        self.btn_menu.setObjectName("HeaderMenuBtn")
        self.btn_menu.setText("☰")
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_menu.setFixedSize(34, 30)

        menu = QMenu(self.btn_menu)

        act_logout = QAction("로그아웃", self)
        act_uninstall = QAction("프로그램 제거", self)

        menu.addAction(act_logout)
        menu.addSeparator()
        menu.addAction(act_uninstall)

        self.btn_menu.setMenu(menu)

        act_logout.triggered.connect(self.logout_requested.emit)
        act_uninstall.triggered.connect(self.uninstall_requested.emit)

        # ✅ Grid placement:
        # row0: meta + menu button
        # row1: version + (empty)
        right_grid.addWidget(self.meta, 0, 0, 1, 1, Qt.AlignRight)
        right_grid.addWidget(self.btn_menu, 0, 1, 2, 1, Qt.AlignRight | Qt.AlignTop)  # 버튼은 2행 높이 사용
        right_grid.addWidget(self.ver, 1, 0, 1, 1, Qt.AlignRight)

        layout.addLayout(left, 1)
        layout.addWidget(right_wrap, 0, Qt.AlignRight)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)