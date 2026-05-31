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
    QWidget,
)

from app.version import __version__


class Header(QWidget):
    home_requested = Signal()
    editor_requested = Signal()
    export_settings_requested = Signal()
    import_settings_requested = Signal()
    environment_changed = Signal(str)
    open_logs_requested = Signal()
    open_backups_requested = Signal()
    send_support_requested = Signal()
    open_support_chat_requested = Signal()
    logout_requested = Signal()
    uninstall_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AppHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(10)

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
        act_env_personal = QAction("개인 PC", self)
        act_env_public = QAction("공용 PC", self)
        act_env_personal.setCheckable(True)
        act_env_public.setCheckable(True)
        act_env_public.setChecked(True)
        act_open_logs = QAction("로그 폴더 열기", self)
        act_open_backups = QAction("백업 폴더 열기", self)
        act_send_support = QAction("오류내용 운영자에게 보내기", self)
        act_open_support = QAction("1:1 문의하기", self)
        act_logout = QAction("로그아웃", self)
        act_uninstall = QAction("프로그램 제거", self)
        env_menu = menu.addMenu("사용 환경")
        env_menu.addAction(act_env_public)
        env_menu.addAction(act_env_personal)
        menu.addAction(act_export_settings)
        menu.addAction(act_import_settings)
        menu.addSeparator()
        menu.addAction(act_open_logs)
        menu.addAction(act_open_backups)
        menu.addAction(act_send_support)
        menu.addAction(act_open_support)
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
        act_env_personal.triggered.connect(lambda: self._select_environment("personal"))
        act_env_public.triggered.connect(lambda: self._select_environment("public"))
        act_open_logs.triggered.connect(self.open_logs_requested.emit)
        act_open_backups.triggered.connect(self.open_backups_requested.emit)
        act_send_support.triggered.connect(self.send_support_requested.emit)
        act_open_support.triggered.connect(self.open_support_chat_requested.emit)
        act_logout.triggered.connect(self.logout_requested.emit)
        act_uninstall.triggered.connect(self.uninstall_requested.emit)
        self.btn_home.clicked.connect(self.home_requested.emit)
        self.btn_editor.clicked.connect(self.editor_requested.emit)
        self._env_actions = {"personal": act_env_personal, "public": act_env_public}

        right_grid.addWidget(self.meta, 0, 0, 1, 1, Qt.AlignRight)
        right_grid.addWidget(self.ver, 1, 0, 1, 1, Qt.AlignRight)

        layout.addStretch(1)
        layout.addLayout(nav)
        layout.addWidget(right_wrap, 0, Qt.AlignRight)
        self.set_mode("home")

    def set_subtitle(self, text: str) -> None:
        pass

    def set_mode(self, mode: str) -> None:
        is_editor = mode == "editor"
        self.btn_home.setChecked(not is_editor)
        self.btn_editor.setChecked(is_editor)

    def set_environment(self, mode: str) -> None:
        mode = "personal" if mode == "personal" else "public"
        for key, action in getattr(self, "_env_actions", {}).items():
            action.setChecked(key == mode)

    def _select_environment(self, mode: str) -> None:
        mode = "personal" if mode == "personal" else "public"
        self.set_environment(mode)
        self.environment_changed.emit(mode)
