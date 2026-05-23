# src/frontend/layout/header.py
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.version import __display_name__, __version__


class Header(QWidget):
    home_requested = Signal()
    editor_requested = Signal()
    export_settings_requested = Signal()
    import_settings_requested = Signal()
    logout_requested = Signal()
    uninstall_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AppHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(3)

        self.title = QLabel(__display_name__)
        self.title.setObjectName("AppTitle")

        self.subtitle = QLabel("-")
        self.subtitle.setObjectName("SubTitle")

        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        nav = QHBoxLayout()
        nav.setSpacing(4)

        self.btn_home = QPushButton("카센더")
        self.btn_home.setObjectName("TopNavButton")
        self.btn_home.setCheckable(True)
        self.btn_home.setCursor(Qt.PointingHandCursor)

        self.btn_editor = QPushButton("편집")
        self.btn_editor.setObjectName("TopNavButton")
        self.btn_editor.setCheckable(True)
        self.btn_editor.setCursor(Qt.PointingHandCursor)

        self.btn_menu = QToolButton()
        self.btn_menu.setObjectName("HeaderMenuBtn")
        self.btn_menu.setText("설정")
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_menu.setToolButtonStyle(Qt.ToolButtonTextOnly)

        menu = QMenu(self.btn_menu)
        act_export_settings = QAction("설정 내보내기", self)
        act_import_settings = QAction("설정 가져오기", self)
        act_logout = QAction("로그아웃", self)
        act_uninstall = QAction("프로그램 제거", self)
        menu.addAction(act_export_settings)
        menu.addAction(act_import_settings)
        menu.addSeparator()
        menu.addAction(act_logout)
        menu.addSeparator()
        menu.addAction(act_uninstall)
        self.btn_menu.setMenu(menu)

        nav.addWidget(self.btn_home)
        nav.addWidget(self.btn_editor)
        nav.addWidget(self.btn_menu)

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

        ver = (__version__ or "").strip()
        if ver and ver != "__VERSION__" and not ver.startswith("v"):
            ver = f"v{ver}"
        self.ver = QLabel(ver if ver and ver != "__VERSION__" else "")
        self.ver.setVisible(bool(self.ver.text()))
        self.ver.setObjectName("Meta")
        self.ver.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ver.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        act_export_settings.triggered.connect(self.export_settings_requested.emit)
        act_import_settings.triggered.connect(self.import_settings_requested.emit)
        act_logout.triggered.connect(self.logout_requested.emit)
        act_uninstall.triggered.connect(self.uninstall_requested.emit)
        self.btn_home.clicked.connect(self.home_requested.emit)
        self.btn_editor.clicked.connect(self.editor_requested.emit)

        right_grid.addWidget(self.meta, 0, 0, 1, 1, Qt.AlignRight)
        right_grid.addWidget(self.ver, 1, 0, 1, 1, Qt.AlignRight)

        layout.addLayout(left, 1)
        layout.addLayout(nav)
        layout.addWidget(right_wrap, 0, Qt.AlignRight)
        self.set_mode("home")

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)

    def set_mode(self, mode: str) -> None:
        is_editor = mode == "editor"
        self.btn_home.setChecked(not is_editor)
        self.btn_editor.setChecked(is_editor)
