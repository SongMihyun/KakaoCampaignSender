from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.version import __version__
from backend.core.app_settings import get_setting, set_setting
from backend.domains.auth import AuthError, AuthService, AuthSession


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resolve_icon_path() -> str:
    base = _app_base_dir()
    candidates = [
        base / "installer" / "dist" / "KakaoSender.ico",
        base / "installer" / "KakaoSender.ico",
        base / "KakaoSender.ico",
        base / "KakaoCampaignSender.ico",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def resolve_logo_path() -> str:
    base = _app_base_dir()
    candidates = [
        base / "installer" / "logo.png",
        base / "_internal" / "installer" / "logo.png",
        base / "logo.png",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def resolve_auth_logo_path(name: str) -> str:
    base = _app_base_dir()
    candidates = [
        base / "src" / "frontend" / "assets" / "auth" / name,
        base / "_internal" / "frontend" / "assets" / "auth" / name,
        base / "frontend" / "assets" / "auth" / name,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


ICON_PATH = resolve_icon_path()
LOGO_PATH = resolve_logo_path()


class LogoWidget(QWidget):
    def __init__(self, size: int = 210, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("카센더")
        label.setObjectName("LogoFallback")
        label.setAlignment(Qt.AlignCenter)

        pixmap = QPixmap()
        if LOGO_PATH:
            pixmap = QPixmap(LOGO_PATH)
        elif ICON_PATH:
            pixmap = QIcon(ICON_PATH).pixmap(size, size)

        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        layout.addWidget(label)


class ProviderButton(QFrame):
    clicked = Signal()

    def __init__(
        self,
        *,
        title: str,
        provider: str,
        icon_path: str,
        trailing: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProviderButton")
        self.setProperty("provider", provider)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 12, 20, 12)
        layout.setSpacing(18)

        icon = QLabel()
        icon.setObjectName("ProviderIcon")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignCenter)
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                icon.setPixmap(
                    pixmap.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        text = QLabel(title)
        text.setObjectName("ProviderTitle")
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        right = QLabel(trailing)
        right.setObjectName("ProviderTrailing")
        right.setFixedWidth(74)
        right.setAlignment(Qt.AlignCenter)

        layout.addWidget(icon)
        layout.addWidget(text)
        layout.addWidget(right)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class LoginDialog(QDialog):
    def __init__(self, auth_service: AuthService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.auth_service = auth_service or AuthService()
        self.session: AuthSession | None = None
        self._beta_fail_count = 0
        self._beta_locked_until: datetime | None = None

        if ICON_PATH:
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setWindowTitle("카센더 로그인")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(540, 900)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)

        self.card = QWidget()
        self.card.setObjectName("LoginCard")
        outer.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(15, 23, 42, 46))
        self.card.setGraphicsEffect(shadow)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 34)
        root.setSpacing(0)

        root.addWidget(self._build_top_controls())

        content = QWidget()
        content.setObjectName("LoginContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(46, 28, 46, 0)
        content_layout.setSpacing(14)

        content_layout.addWidget(LogoWidget(size=380), 0, Qt.AlignHCenter)
        content_layout.addSpacing(18)

        self.btn_kakao = ProviderButton(
            title="카카오톡 로그인",
            provider="kakao",
            icon_path=resolve_auth_logo_path("kakao_talk_logo.png"),
            trailing=">",
        )
        self.btn_google = ProviderButton(
            title="구글 로그인",
            provider="google",
            icon_path=resolve_auth_logo_path("google_logo.png"),
            trailing="준비중",
        )
        self.btn_naver = ProviderButton(
            title="네이버 로그인",
            provider="naver",
            icon_path=resolve_auth_logo_path("naver_logo.png"),
            trailing="준비중",
        )

        self.btn_kakao.clicked.connect(self._login)
        self.btn_google.clicked.connect(lambda: self._show_coming_soon("구글 로그인"))
        self.btn_naver.clicked.connect(lambda: self._show_coming_soon("네이버 로그인"))

        content_layout.addWidget(self.btn_kakao)
        content_layout.addWidget(self.btn_google)
        content_layout.addWidget(self.btn_naver)

        self.status = QLabel("")
        self.status.setObjectName("LoginStatus")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        content_layout.addWidget(self.status)

        notice_line = QWidget()
        notice_line.setObjectName("NoticeLine")
        notice_line.setFixedHeight(1)
        content_layout.addWidget(notice_line)

        notice = QLabel(
            "카센더는 카카오톡 공식서비스가 아닙니다.\n"
            "로그인은 사용자인증 관리 목적으로만 사용됩니다."
        )
        notice.setObjectName("LoginNotice")
        notice.setAlignment(Qt.AlignCenter)
        notice.setWordWrap(True)
        content_layout.addWidget(notice)

        version = (__version__ or "").strip()
        if version and version != "__VERSION__" and not version.startswith("v"):
            version = f"v{version}"
        version_label = QLabel(f"{version or 'v1.0.5'} Beta")
        version_label.setObjectName("VersionLabel")
        version_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(version_label)

        root.addWidget(content)
        self._apply_style()

    def _build_top_controls(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("LoginTopControls")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 0)
        layout.setSpacing(8)

        env_wrap = QWidget()
        env_wrap.setObjectName("PcModeSelector")
        env_layout = QHBoxLayout(env_wrap)
        env_layout.setContentsMargins(4, 4, 4, 4)
        env_layout.setSpacing(4)
        self.btn_env_public = QPushButton("공용")
        self.btn_env_public.setObjectName("PcModeButton")
        self.btn_env_public.setCheckable(True)
        self.btn_env_public.setCursor(Qt.PointingHandCursor)
        self.btn_env_personal = QPushButton("개인")
        self.btn_env_personal.setObjectName("PcModeButton")
        self.btn_env_personal.setCheckable(True)
        self.btn_env_personal.setCursor(Qt.PointingHandCursor)
        env_layout.addWidget(self.btn_env_public)
        env_layout.addWidget(self.btn_env_personal)
        layout.addWidget(env_wrap, 0, Qt.AlignLeft | Qt.AlignTop)
        layout.addStretch(1)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("TopIconBtn")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self._show_settings_menu)

        self.settings_menu = QMenu(self)
        if self.auth_service.config.beta_password_login_enabled:
            act_beta = QAction("비상용", self)
            act_beta.triggered.connect(self._open_beta_login)
            self.settings_menu.addAction(act_beta)
        act_uninstall = QAction("프로그램 삭제", self)
        act_uninstall.triggered.connect(self._uninstall_application)
        self.settings_menu.addAction(act_uninstall)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TopIconBtn")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.reject)

        layout.addWidget(self.btn_settings)
        layout.addWidget(self.btn_close)
        self.btn_env_public.clicked.connect(lambda: self._select_pc_environment("public"))
        self.btn_env_personal.clicked.connect(lambda: self._select_pc_environment("personal"))
        self._apply_pc_environment(str(get_setting("pc_environment", "public") or "public"))
        return bar

    def _select_pc_environment(self, mode: str) -> None:
        mode = "personal" if mode == "personal" else "public"
        if mode == "personal":
            reply = QMessageBox.warning(
                self,
                "개인 PC 로그인 안내",
                "<b>개인 PC로 선택하면 로그인 유지 기간이 1주일로 설정됩니다.</b><br><br>"
                "<span style='color:#dc2626; font-weight:900;'>중요: 공용 PC에서는 절대 사용하지 마세요.</span><br><br>"
                "이 PC가 본인만 사용하는 개인 PC가 맞습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                mode = "public"
        set_setting("pc_environment", mode)
        if mode == "public":
            self.auth_service.clear_session()
        self._apply_pc_environment(mode)

    def _apply_pc_environment(self, mode: str) -> None:
        mode = "personal" if mode == "personal" else "public"
        self.btn_env_public.setChecked(mode == "public")
        self.btn_env_personal.setChecked(mode == "personal")

    def _show_settings_menu(self) -> None:
        pos = self.btn_settings.mapToGlobal(self.btn_settings.rect().bottomLeft())
        self.settings_menu.exec(pos)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#LoginCard {
                background: #ffffff;
                border: 1px solid #d9dee7;
                border-radius: 18px;
            }
            QWidget#LoginTopControls {
                background: transparent;
            }
            QWidget#PcModeSelector {
                background: #f8fafc;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
            QPushButton#PcModeButton {
                background: transparent;
                border: none;
                border-radius: 9px;
                color: #64748b;
                font-size: 13px;
                font-weight: 800;
                min-width: 48px;
                min-height: 28px;
                max-height: 28px;
            }
            QPushButton#PcModeButton:checked {
                background: #111827;
                color: #ffffff;
            }
            QPushButton#PcModeButton:hover {
                background: #e5e7eb;
                color: #111827;
            }
            QPushButton#PcModeButton:checked:hover {
                background: #111827;
                color: #ffffff;
            }
            QPushButton#TopIconBtn {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #111827;
                font-size: 22px;
                font-weight: 800;
                min-width: 38px;
                min-height: 34px;
                max-width: 38px;
                max-height: 34px;
            }
            QPushButton#TopIconBtn:hover {
                background: #f3f4f6;
            }
            QMenu {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 6px;
                color: #111827;
                font-size: 14px;
            }
            QMenu::item {
                padding: 9px 18px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #f3f4f6;
            }
            QLabel#LoginTitle {
                color: #111827;
                font-size: 38px;
                font-weight: 900;
            }
            QLabel#LoginDesc {
                color: #3f4652;
                font-size: 18px;
                line-height: 1.5;
            }
            QLabel#SectionLabel {
                color: #6b7280;
                font-size: 13px;
                font-weight: 800;
                margin-top: 8px;
            }
            QLabel#LogoFallback {
                color: #111827;
                font-size: 28px;
                font-weight: 900;
            }
            QFrame#ProviderButton {
                background: #ffffff;
                border: 1px solid #e0e3e9;
                border-radius: 18px;
            }
            QFrame#ProviderButton[provider="kakao"] {
                border: 2px solid #f2c300;
            }
            QFrame#ProviderButton[provider="kakao"]:hover {
                background: #fffdf2;
            }
            QFrame#ProviderButton[provider="google"]:hover,
            QFrame#ProviderButton[provider="naver"]:hover {
                background: #f9fafb;
            }
            QLabel#ProviderTitle {
                background: transparent;
                color: #111827;
                font-size: 21px;
                font-weight: 900;
            }
            QLabel#ProviderTrailing {
                background: transparent;
                color: #111827;
                font-size: 20px;
                font-weight: 900;
            }
            QLabel#ProviderIcon {
                background: transparent;
            }
            QLabel#LoginStatus {
                min-height: 28px;
                color: #6b7280;
                font-size: 13px;
            }
            QWidget#NoticeLine {
                background: #e5e7eb;
                margin-top: 6px;
            }
            QLabel#LoginNotice {
                color: #6b7280;
                font-size: 14px;
                line-height: 1.5;
            }
            QLabel#VersionLabel {
                color: #8a93a3;
                font-size: 15px;
                font-weight: 800;
                margin-top: 8px;
            }
            """
        )

    def _login(self) -> None:
        self.btn_kakao.setEnabled(False)
        self.status.setText("브라우저에서 카카오 로그인을 진행해 주세요.")
        try:
            self.session = self.auth_service.login_with_kakao()
        except AuthError as e:
            self.status.setText("")
            QMessageBox.warning(self, "로그인 실패", _friendly_login_error(str(e)))
            self.btn_kakao.setEnabled(True)
            return
        self.accept()

    def _show_coming_soon(self, name: str) -> None:
        QMessageBox.information(self, "준비중", f"{name}은 준비중입니다.")

    def _open_beta_login(self) -> None:
        now = datetime.now()
        if self._beta_locked_until and now < self._beta_locked_until:
            remain = max(1, int((self._beta_locked_until - now).total_seconds() // 60) + 1)
            QMessageBox.warning(self, "비상 로그인 잠금", f"로그인 실패가 반복되어 잠시 잠금되었습니다.\n{remain}분 후 다시 시도해 주세요.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("비상 로그인")
        dlg.setModal(True)
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        desc = QLabel("카카오 로그인에 문제가 있는 베타 사용자를 위한 임시 로그인입니다.")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        txt_id = QLineEdit()
        txt_id.setPlaceholderText("아이디")
        txt_id.setMinimumHeight(42)
        layout.addWidget(txt_id)

        txt_pw = QLineEdit()
        txt_pw.setPlaceholderText("비밀번호")
        txt_pw.setEchoMode(QLineEdit.Password)
        txt_pw.setMinimumHeight(42)
        layout.addWidget(txt_pw)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("로그인")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        layout.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return

        try:
            self.session = self.auth_service.login_with_beta_password(
                txt_id.text().strip(),
                txt_pw.text(),
            )
        except AuthError as e:
            self._beta_fail_count += 1
            if self._beta_fail_count >= 5:
                self._beta_locked_until = datetime.now() + timedelta(minutes=5)
                QMessageBox.warning(self, "비상 로그인 실패", "5회 실패하여 5분 동안 잠금되었습니다.")
            else:
                left = 5 - self._beta_fail_count
                QMessageBox.warning(self, "비상 로그인 실패", f"{e}\n남은 시도 횟수: {left}회")
            return

        self._beta_fail_count = 0
        self._beta_locked_until = None
        self.accept()

    def _uninstall_application(self) -> None:
        root = Path(getattr(sys, "_MEIPASS", _app_base_dir()))
        ps1 = root / "uninstall.ps1"
        if not ps1.exists():
            QMessageBox.information(self, "안내", f"삭제 스크립트를 찾을 수 없습니다.\n{ps1}")
            return

        reply = QMessageBox.warning(
            self,
            "프로그램 삭제",
            "프로그램 삭제를 시작합니다.\n진행 중 앱이 종료될 수 있습니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.auth_service.clear_session()
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps1),
                ],
                cwd=str(root),
                creationflags=flags,
            )
            self.reject()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실행 실패\n{e}")

    @staticmethod
    def run_login(auth_service: AuthService | None = None, parent=None) -> AuthSession | None:
        dlg = LoginDialog(auth_service=auth_service, parent=parent)
        if dlg.exec() == QDialog.Accepted:
            return dlg.session
        return None


def _friendly_login_error(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "네트워크 상태를 확인해 주세요."
    if "access_denied" in text or "cancel" in text.lower():
        return "로그인이 취소되었습니다."
    if "KAKAO_CLIENT_ID" in text or "KAKAO_REDIRECT_URI" in text:
        return text
    return text


__all__ = ["LoginDialog", "resolve_icon_path", "resolve_logo_path"]
