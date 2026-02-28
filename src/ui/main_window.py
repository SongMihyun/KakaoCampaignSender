from __future__ import annotations

import sys
import subprocess
import os

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QMessageBox,
    QApplication,
)

from app.paths import contacts_db_path
from app.data.contacts_repo import ContactsRepo
from app.data.groups_repo import GroupsRepo
from app.data.campaigns_repo import CampaignsRepo
from app.data.send_lists_repo import SendListsRepo
from app.data.send_logs_repo import SendLogsRepo

from app.stores.contacts_store import ContactsStore
from app.system.reset_app import schedule_delete_all_local_data
from app.version import __display_name__

from ui.layout.header import Header
from ui.layout.navigation import Navigation
from ui.layout.statusbar import StatusBar

from ui.pages.contacts_page import ContactsPage
from ui.pages.groups_page import GroupsPage
from ui.pages.campaign_page import CampaignPage
from ui.pages.send_page import SendPage
from ui.pages.logs_page import LogsPage


class MainWindow(QMainWindow):
    TITLES = ["대상자 관리", "발송 그룹", "캠페인 설정", "발송", "로그/리포트"]

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(__display_name__)
        self.resize(1180, 760)

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.header = Header()
        self.header.logout_requested.connect(self.logout)
        self.header.uninstall_requested.connect(self.uninstall_application)

        self.nav = Navigation()
        self.status = StatusBar()
        self.stack = QStackedWidget()

        # -------------------------
        # Repos / Store
        # -------------------------
        db_path = contacts_db_path()

        self.contacts_repo = ContactsRepo(db_path)
        self.groups_repo = GroupsRepo(db_path)
        self.campaigns_repo = CampaignsRepo(db_path)
        self.send_lists_repo = SendListsRepo(db_path)

        self.send_logs_repo = SendLogsRepo(db_path)
        self.send_logs_repo.ensure_tables()

        self.contacts_store = ContactsStore()

        # ✅ 이벤트 허브(전역 동기화) - 로딩 성공/실패와 무관하게 항상 연결
        from ui.app_events import app_events
        app_events.contacts_changed.connect(self._on_contacts_changed_global)  # type: ignore[attr-defined]

        # ✅ 최초 1회 로딩 (list_all/search_contacts 중 하나로 통일)
        try:
            self.contacts_store.load_rows(self.contacts_repo.list_all())
        except Exception:
            # 최후수단
            try:
                self.contacts_store.load_rows(self.contacts_repo.search_contacts(""))
            except Exception:
                self.contacts_store.clear()

        # -------------------------
        # Pages
        # -------------------------
        self.contacts_page = ContactsPage(
            repo=self.contacts_repo,
            contacts_store=self.contacts_store,
            on_status=self.status.set_message
        )

        self.groups_page = GroupsPage(
            repo=self.groups_repo,
            contacts_repo=self.contacts_repo,
            contacts_store=self.contacts_store,
            on_status=self.status.set_message
        )

        self.campaign_page = CampaignPage(
            repo=self.campaigns_repo,
            on_status=self.status.set_message
        )

        self.send_page = SendPage(
            contacts_repo=self.contacts_repo,
            groups_repo=self.groups_repo,
            contacts_store=self.contacts_store,
            campaigns_repo=self.campaigns_repo,
            send_lists_repo=self.send_lists_repo,
            send_logs_repo=self.send_logs_repo,
            on_progress=self.status.set_progress,
            on_status=self.status.set_message,
        )

        self.logs_page = LogsPage(
            logs_repo=self.send_logs_repo,
            campaigns_repo=self.campaigns_repo,
            on_reset_all=self.reset_application,
        )

        self.stack.addWidget(self.contacts_page)  # 0
        self.stack.addWidget(self.groups_page)    # 1
        self.stack.addWidget(self.campaign_page)  # 2
        self.stack.addWidget(self.send_page)      # 3
        self.stack.addWidget(self.logs_page)      # 4

        center = QWidget()
        center.setLayout(self.nav.build_layout(self.stack))

        root_layout.addWidget(self.header)
        root_layout.addWidget(center, 1)
        root_layout.addWidget(self.status)

        self.nav.page_changed.connect(self._go_page)
        self._go_page(0)
        self._apply_style()

    def closeEvent(self, event) -> None:
        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

        try:
            from app.updater import launch_installer_if_pending
            launch_installer_if_pending()
        except Exception:
            pass

        super().closeEvent(event)

    def _go_page(self, idx: int) -> None:
        if idx < 0 or idx >= self.stack.count():
            return

        self.nav.set_current(idx)
        self.stack.setCurrentIndex(idx)

        title = self.TITLES[idx] if idx < len(self.TITLES) else f"Page {idx}"
        self.header.set_subtitle(title)
        self.status.set_message(f"Ready | {title}")

        try:
            if idx == 4 and hasattr(self, "logs_page") and self.logs_page:
                self.logs_page.refresh()
        except Exception:
            pass

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #f6f7fb; }

            QWidget#Card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }

            QLabel#AppTitle { font-size: 18px; font-weight: 800; }
            QLabel#SubTitle { font-size: 13px; color: #6b7280; }
            QLabel#Meta { font-size: 12px; color: #6b7280; }

            QListWidget {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 6px;
                font-size: 13px;
            }
            QListWidget::item { padding: 10px 12px; border-radius: 10px; margin: 2px 0; }

            QListWidget::item:selected {
                background: #e8efff;
                color: #111827;
            }
            QListWidget::item:selected:active {
                background: #e8efff;
                color: #111827;
            }
            QListWidget::item:selected:!active {
                background: #e8efff;
                color: #111827;
            }

            QWidget#Page {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
            QLabel#PageTitle { font-size: 18px; font-weight: 800; }
            QLabel#PageDesc { font-size: 12px; color: #6b7280; }

            QPushButton {
                padding: 8px 12px;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
            }
            QPushButton:hover { background: #f3f4f6; }

            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                padding: 8px 10px;
                background: #ffffff;
            }

            QToolButton#HeaderMenuBtn {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                background: #ffffff;
                padding: 0px 6px;
                font-weight: 900;
            }
            QToolButton#HeaderMenuBtn:hover {
                background: #f3f4f6;
            }
        """)

    def _load_contacts_store_from_db(self) -> int:
        all_rows = self.contacts_repo.search_contacts("")
        self.contacts_store.load_rows(all_rows)
        return len(all_rows)

    def _on_contacts_changed_global(self) -> None:
        # 1) 디바운스 타이머 준비(최초 1회 생성)
        if not hasattr(self, "_contacts_sync_timer"):
            from PySide6.QtCore import QTimer
            self._contacts_sync_timer = QTimer(self)  # type: ignore[attr-defined]
            self._contacts_sync_timer.setSingleShot(True)  # type: ignore[attr-defined]
            self._contacts_sync_timer.timeout.connect(self._do_contacts_store_sync_bg)  # type: ignore[attr-defined]

        try:
            self._contacts_sync_timer.start(120)  # type: ignore[attr-defined]
        except Exception:
            self._do_contacts_store_sync_bg()

    def _do_contacts_store_sync_bg(self) -> None:
        try:
            from ui.utils.worker import run_bg
        except Exception:
            try:
                cnt = self._load_contacts_store_from_db()
                self.status.set_message(f"대상자 캐시 동기화 완료: {cnt}건")
            except Exception as e:
                self.status.set_message(f"대상자 캐시 동기화 실패: {e}")
            return

        def job():
            return self.contacts_repo.search_contacts("")

        def done(all_rows):
            try:
                self.contacts_store.load_rows(all_rows)
                self._refresh_pages_after_contacts_sync()
                self.status.set_message(f"대상자 캐시 동기화 완료: {len(all_rows)}건")
            except Exception as e:
                self.status.set_message(f"대상자 캐시 반영 실패: {e}")

        def err(tb: str):
            self.status.set_message(f"대상자 캐시 동기화 실패: {tb}")

        run_bg(job, on_done=done, on_error=err)

    def _refresh_pages_after_contacts_sync(self) -> None:
        try:
            if hasattr(self, "groups_page") and self.groups_page:
                if hasattr(self.groups_page, "refresh_candidates"):
                    self.groups_page.refresh_candidates()
                if hasattr(self.groups_page, "refresh"):
                    self.groups_page.refresh()
        except Exception:
            pass

        try:
            if hasattr(self, "send_page") and self.send_page:
                if hasattr(self.send_page, "refresh"):
                    self.send_page.refresh()
                if hasattr(self.send_page, "refresh_groups"):
                    self.send_page.refresh_groups()
        except Exception:
            pass

    def reset_application(self) -> None:
        reply = QMessageBox.question(
            self,
            "전체 초기화",
            "모든 로컬 데이터(DB 포함)를 삭제하고 프로그램을 종료합니다.\n"
            "프로그램 종료 후 자동으로 삭제가 진행됩니다.\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

        try:
            log_path = schedule_delete_all_local_data()
        except Exception as e:
            QMessageBox.critical(self, "삭제 예약 실패", f"삭제 예약 중 오류:\n{e}")
            return

        QMessageBox.information(
            self,
            "완료",
            "프로그램을 종료합니다.\n"
            "종료 후 로컬 데이터가 자동으로 삭제됩니다.\n\n"
            f"삭제 로그: {log_path}",
        )

        QApplication.quit()
        sys.exit(0)

    def logout(self) -> None:
        reply = QMessageBox.question(
            self,
            "로그아웃",
            "로그아웃 하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from ui.dialogs.login_dialog import LoginDialog
        except Exception:
            QMessageBox.information(self, "안내", "LoginDialog를 찾을 수 없습니다.")
            return

        self.hide()
        ok = LoginDialog.run_login(self)
        if ok:
            self.show()
            self._go_page(0)
        else:
            self.close()

    def uninstall_application(self) -> None:
        reply = QMessageBox.question(
            self,
            "프로그램 제거",
            "프로그램 제거(언인스톨)를 실행합니다.\n"
            "제거가 시작되면 프로그램은 종료됩니다.\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

        uninst = os.path.join(os.path.dirname(sys.executable), "unins000.exe")

        if not os.path.exists(uninst):
            QMessageBox.warning(
                self,
                "언인스톨러 없음",
                "언인스톨러(unins000.exe)를 찾지 못했습니다.\n"
                "Windows '앱 및 기능'에서 카센더를 제거해주세요.",
            )
            return

        try:
            subprocess.Popen([uninst], shell=False)
        except Exception as e:
            QMessageBox.critical(self, "제거 실행 실패", f"제거 실행 중 오류:\n{e}")
            return

        QApplication.quit()
        sys.exit(0)