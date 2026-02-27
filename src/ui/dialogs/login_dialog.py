# src/ui/dialogs/login_dialog.py
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLineEdit, QPushButton, QMessageBox,
    QGraphicsDropShadowEffect, QLabel, QCheckBox
)

# ✅ 하드코딩 계정
LOGIN_ID = "mimi"
LOGIN_PW = "qwer1234!!"


def _app_base_dir() -> Path:
    # ✅ 설치형(PyInstaller)이면 exe 기준, 개발이면 repo 기준 추정
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/ui/dialogs/login_dialog.py -> repo root 추정
    return Path(__file__).resolve().parents[3]


def resolve_icon_path() -> str:
    base = _app_base_dir()

    candidates = [
        # ✅ 개발환경(레포)
        base / "installer" / "dist" / "KakaoSender.ico",
        base / "installer" / "KakaoSender.ico",

        # ✅ 설치환경(설치 폴더에 복사된 아이콘)
        base / "KakaoSender.ico",
        base / "KakaoCampaignSender.ico",
    ]

    for p in candidates:
        if p.exists():
            return str(p)
    return ""


ICON_PATH = resolve_icon_path()


def load_icon_pixmap(size: int = 180):
    """
    ✅ ICO는 QIcon(path).pixmap(...)로 뽑는 방식이 가장 안정적입니다.
    """
    if not ICON_PATH:
        return None
    ico = QIcon(ICON_PATH)
    pm = ico.pixmap(size, size)
    return None if pm.isNull() else pm


# -----------------------------
# Logo widget (ICO image)
# -----------------------------
class LogoWidget(QWidget):
    def __init__(self, size: int = 210, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)

        pm = load_icon_pixmap(size)
        if pm is not None:
            self.label.setPixmap(pm)
        else:
            self.label.setText("카센더")

        layout.addWidget(self.label)


# -----------------------------
# Main dialog
# -----------------------------
class LoginDialog(QDialog):
    # ✅ 설정 저장 키(QSettings)
    # 회사/앱명은 충돌만 안 나면 됩니다.
    ORG_NAME = "Kasender"
    APP_NAME = "Kasender"

    KEY_REMEMBER = "login/remember"
    KEY_ID = "login/id"
    KEY_PW = "login/pw"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # ✅ 창 아이콘
        if ICON_PATH:
            self.setWindowIcon(QIcon(ICON_PATH))

        # ✅ frameless like screenshot
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # ✅ 카톡 느낌: 살짝 더 세로로
        self.setFixedSize(560, 800)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)

        self.card = QWidget()
        self.card.setObjectName("LoginCard")
        outer.addWidget(self.card)

        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30)
        sh.setOffset(0, 10)
        sh.setColor(QColor(0, 0, 0, 80))
        self.card.setGraphicsEffect(sh)

        root = QVBoxLayout(self.card)
        # ✅ 내부 여백 줄여서 전체가 위로 올라오게
        root.setContentsMargins(26, 18, 26, 22)
        root.setSpacing(10)

        # top close row (X 버튼)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch(1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setFixedSize(40, 34)
        self.btn_close.clicked.connect(self.reject)

        top.addWidget(self.btn_close)
        root.addLayout(top)

        # ✅ 상단 여백(중앙 정렬용)
        root.addStretch(1)

        root.addSpacing(4)
        root.addWidget(LogoWidget(size=210), 0, Qt.AlignHCenter)  # 로고도 조금 키움
        root.addSpacing(12)

        # inputs area (가로 폭/위치 조정)
        form = QVBoxLayout()
        form.setSpacing(12)
        form.setContentsMargins(72, 0, 72, 0)

        self.cbo_id = QComboBox()
        self.cbo_id.setEditable(True)
        self.cbo_id.setObjectName("IdBox")
        self.cbo_id.setInsertPolicy(QComboBox.NoInsert)
        self.cbo_id.setMinimumHeight(64)
        self.cbo_id.setPlaceholderText("아이디")

        self.txt_pw = QLineEdit()
        self.txt_pw.setObjectName("PwBox")
        self.txt_pw.setEchoMode(QLineEdit.Password)
        self.txt_pw.setPlaceholderText("비밀번호")
        self.txt_pw.setMinimumHeight(64)

        # ✅ 저장 체크박스 추가
        self.chk_remember = QCheckBox("아이디/비밀번호 저장")
        self.chk_remember.setObjectName("RememberChk")

        self.btn_login = QPushButton("로그인")
        self.btn_login.setObjectName("LoginBtn")
        self.btn_login.setMinimumHeight(68)

        form.addWidget(self.cbo_id)
        form.addWidget(self.txt_pw)
        form.addWidget(self.chk_remember)
        form.addWidget(self.btn_login)

        root.addLayout(form)

        # ✅ 하단 여백(중앙 정렬 + 노란 영역 확보)
        root.addStretch(2)

        # wire
        self.btn_login.clicked.connect(self._try_login)
        if self.cbo_id.lineEdit():
            self.cbo_id.lineEdit().returnPressed.connect(self._try_login)
        self.txt_pw.returnPressed.connect(self._try_login)

        self._apply_style()

        # ✅ 저장된 값 로드(여기서 자동 채움)
        self._load_saved_login()

        # 포커스: 아이디가 있으면 비번으로, 없으면 아이디로
        if (self.cbo_id.currentText() or "").strip():
            self.txt_pw.setFocus()
        else:
            self.cbo_id.setFocus()

    # -------------------------
    # Settings
    # -------------------------
    def _settings(self) -> QSettings:
        return QSettings(self.ORG_NAME, self.APP_NAME)

    def _load_saved_login(self) -> None:
        s = self._settings()
        remember = bool(s.value(self.KEY_REMEMBER, False, type=bool))
        saved_id = str(s.value(self.KEY_ID, "", type=str) or "")
        saved_pw = str(s.value(self.KEY_PW, "", type=str) or "")

        self.chk_remember.setChecked(remember)

        if saved_id:
            # 콤보에 없으면 추가 후 세팅
            if self.cbo_id.findText(saved_id) < 0:
                self.cbo_id.addItem(saved_id)
            self.cbo_id.setCurrentText(saved_id)

        # 비밀번호는 체크된 경우에만 복원
        if remember and saved_pw:
            self.txt_pw.setText(saved_pw)

    def _save_or_clear_login(self) -> None:
        s = self._settings()

        uid = (self.cbo_id.currentText() or "").strip()
        pw = (self.txt_pw.text() or "").strip()
        remember = self.chk_remember.isChecked()

        # 아이디는 편의상 항상 저장
        s.setValue(self.KEY_ID, uid)

        if remember:
            s.setValue(self.KEY_REMEMBER, True)
            s.setValue(self.KEY_PW, pw)   # ✅ 요청대로 비번도 저장(평문)
        else:
            s.setValue(self.KEY_REMEMBER, False)
            s.setValue(self.KEY_PW, "")   # 저장 해제 시 비번 제거

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget#LoginCard {
                background: #FEE500;
                border-radius: 18px;
            }

            QPushButton#CloseBtn {
                background: rgba(255,255,255,0.40);
                border: 1px solid rgba(0,0,0,0.10);
                border-radius: 10px;
                color: #111;
                font-weight: 900;
            }
            QPushButton#CloseBtn:hover { background: rgba(255,255,255,0.60); }

            /* Input-like boxes */
            QComboBox#IdBox, QLineEdit#PwBox {
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 15px;
                color: #111827;
            }

            QComboBox#IdBox::drop-down { border: none; width: 38px; }
            QComboBox#IdBox::down-arrow { width: 10px; height: 10px; }

            QCheckBox#RememberChk {
                spacing: 8px;
                padding-left: 2px;
                font-size: 13px;
                color: rgba(0,0,0,0.65);
            }

            QPushButton#LoginBtn {
                background: rgba(255,255,255,0.55);
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 12px;
                font-size: 18px;
                font-weight: 900;
                color: rgba(0,0,0,0.55);
            }
            QPushButton#LoginBtn:hover { background: rgba(255,255,255,0.75); }
            QPushButton#LoginBtn:pressed { background: rgba(255,255,255,0.65); }
        """)

    def _try_login(self) -> None:
        uid = (self.cbo_id.currentText() or "").strip()
        pw = (self.txt_pw.text() or "").strip()

        if uid == LOGIN_ID and pw == LOGIN_PW:
            # ✅ 로그인 성공 시 저장/해제 처리
            self._save_or_clear_login()
            self.accept()
            return

        QMessageBox.warning(self, "로그인 실패", "아이디 또는 비밀번호가 올바르지 않습니다.")
        self.txt_pw.selectAll()
        self.txt_pw.setFocus()

    @staticmethod
    def run_login(parent=None) -> bool:
        dlg = LoginDialog(parent)
        return dlg.exec() == QDialog.Accepted


__all__ = ["LoginDialog"]