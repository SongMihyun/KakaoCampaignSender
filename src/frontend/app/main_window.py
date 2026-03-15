# FILE: src/frontend/app/main_window.py
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.paths import contacts_db_path
from app.version import __display_name__
from backend.core.lifecycle.apply_settings_bundle import schedule_apply_settings_bundle_after_exit
from backend.core.lifecycle.reset_app import schedule_delete_all_local_data
from backend.domains.campaigns.repository import CampaignsRepo
from backend.domains.campaigns.service import CampaignsService
from backend.domains.contacts.repository import ContactsRepo
from backend.domains.contacts.service import ContactsService
from backend.domains.groups.repository import GroupsRepo
from backend.domains.groups.service import GroupsService
from backend.domains.logs.repository import SendLogsRepo
from backend.domains.logs.service import LogsService
from backend.domains.reports.reader import SendReportReader
from backend.domains.send_lists.repository import SendListsRepo
from backend.domains.send_lists.service import SendListsService
from backend.domains.sending.job_builder import SendJobBuilder
from backend.domains.sending.service import SendingService
from backend.domains.sending.worker import MultiSendWorker
from backend.domains.settings_bundle.service import SettingsBundleService
from backend.stores.contacts_store import ContactsStore

from frontend.layout.header import Header
from frontend.layout.navigation import Navigation
from frontend.layout.statusbar import StatusBar
from frontend.pages.campaigns.page import CampaignPage
from frontend.pages.contacts.page import ContactsPage
from frontend.pages.groups.page import GroupsPage
from frontend.pages.logs.page import LogsPage
from frontend.pages.sending.page import SendPage


class MainWindow(QMainWindow):
    TITLES = ["대상자 관리", "발송 그룹", "캠페인 설정", "발송", "로그/리포트"]

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(__display_name__)
        self.resize(1180, 760)
        self._skip_finalize_pending_update_once = False

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.header = Header()
        self.header.export_settings_requested.connect(self.export_settings_bundle)
        self.header.import_settings_requested.connect(self.import_settings_bundle)
        self.header.logout_requested.connect(self.logout)
        self.header.uninstall_requested.connect(self.uninstall_application)

        self.nav = Navigation()
        self.status = StatusBar()
        self.stack = QStackedWidget()

        db_path = contacts_db_path()

        # repositories
        self.contacts_repo = ContactsRepo(db_path)
        self.groups_repo = GroupsRepo(db_path)
        self.campaigns_repo = CampaignsRepo(db_path)
        self.send_lists_repo = SendListsRepo(db_path)
        self.send_logs_repo = SendLogsRepo(db_path)
        self.send_logs_repo.ensure_tables()

        # stores
        self.contacts_store = ContactsStore()

        # services
        self.contacts_service = ContactsService(
            repo=self.contacts_repo,
            store=self.contacts_store,
        )
        self.groups_service = GroupsService(
            repo=self.groups_repo,
            contacts_repo=self.contacts_repo,
            contacts_store=self.contacts_store,
        )
        self.campaigns_service = CampaignsService(
            repo=self.campaigns_repo,
        )
        self.send_lists_service = SendListsService(
            repo=self.send_lists_repo,
        )
        self.settings_bundle_service = SettingsBundleService()

        self.report_reader = SendReportReader()
        self.logs_service = LogsService(
            repo=self.send_logs_repo,
            report_reader=self.report_reader,
        )

        self.send_job_builder = SendJobBuilder(
            send_lists_service=self.send_lists_service,
            groups_repo=self.groups_repo,
            contacts_store=self.contacts_store,
            campaigns_service=self.campaigns_service,
        )

        self.sending_service = SendingService(
            job_builder=self.send_job_builder,
            worker_factory=MultiSendWorker,
        )

        from frontend.app.app_events import app_events

        app_events.contacts_changed.connect(self._on_contacts_changed_global)  # type: ignore[attr-defined]

        try:
            self.contacts_store.load_rows(self.contacts_repo.list_all())
        except Exception:
            try:
                self.contacts_store.load_rows(self.contacts_repo.search_contacts(""))
            except Exception:
                self.contacts_store.clear()

        # pages
        self.contacts_page = ContactsPage(
            service=self.contacts_service,
            contacts_store=self.contacts_store,
            on_status=self.status.set_message,
        )

        self.groups_page = GroupsPage(
            service=self.groups_service,
            contacts_service=self.contacts_service,
            contacts_store=self.contacts_store,
            on_status=self.status.set_message,
        )

        self.campaign_page = CampaignPage(
            service=self.campaigns_service,
            on_status=self.status.set_message,
        )

        self.send_page = SendPage(
            contacts_service=self.contacts_service,
            contacts_store=self.contacts_store,
            campaigns_service=self.campaigns_service,
            sending_service=self.sending_service,
            send_logs_repo=self.send_logs_repo,
            on_progress=self.status.set_progress,
            on_status=self.status.set_message,
        )

        self.logs_page = LogsPage(
            logs_service=self.logs_service,
            campaigns_service=self.campaigns_service,
            on_reset_all=self.reset_application,
        )

        self.stack.addWidget(self.contacts_page)
        self.stack.addWidget(self.groups_page)
        self.stack.addWidget(self.campaign_page)
        self.stack.addWidget(self.send_page)
        self.stack.addWidget(self.logs_page)

        center = QWidget()
        center.setLayout(self.nav.build_layout(self.stack))

        root_layout.addWidget(self.header)
        root_layout.addWidget(center, 1)
        root_layout.addWidget(self.status)

        self.nav.page_changed.connect(self._go_page)
        self._go_page(0)
        self._apply_style()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_before_close()
        self._finalize_pending_update()
        super().closeEvent(event)

    def _cleanup_before_close(self) -> None:
        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

    def _finalize_pending_update(self) -> None:
        if getattr(self, "_skip_finalize_pending_update_once", False):
            self._skip_finalize_pending_update_once = False
            return
        try:
            from backend.updates.updater import finalize_update_on_app_close

            finalize_update_on_app_close()
        except Exception:
            pass

    def _go_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        title = self.TITLES[index] if 0 <= index < len(self.TITLES) else __display_name__
        self.header.set_subtitle(title)

        try:
            if index == 4 and hasattr(self, "logs_page") and self.logs_page:
                if hasattr(self.logs_page, "refresh"):
                    self.logs_page.refresh()
        except Exception:
            pass

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
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
            """
        )

    def _load_contacts_store_from_db(self) -> int:
        all_rows = self.contacts_repo.search_contacts("")
        self.contacts_store.load_rows(all_rows)
        return len(all_rows)

    def _on_contacts_changed_global(self) -> None:
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
            from frontend.utils.worker import run_bg
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
                if hasattr(self.groups_page, "refresh"):
                    self.groups_page.refresh()
        except Exception:
            pass

        try:
            if hasattr(self, "send_page") and self.send_page:
                if hasattr(self.send_page, "reload_send_lists"):
                    self.send_page.reload_send_lists()
        except Exception:
            pass

    def _is_send_busy(self) -> bool:
        try:
            if hasattr(self, "send_page") and self.send_page:
                if hasattr(self.send_page, "is_sending_active"):
                    return bool(self.send_page.is_sending_active())
        except Exception:
            pass
        return False

    def export_settings_bundle(self) -> None:
        if self._is_send_busy():
            QMessageBox.information(
                self,
                "안내",
                "발송 중에는 설정 내보내기를 할 수 없습니다.\n발송 종료 후 다시 시도해주세요.",
            )
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"kakao_sender_settings_{ts}.kcsbundle"
        default_path = str(Path.home() / "Downloads" / default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "설정 내보내기",
            default_path,
            "카센더 설정 백업 (*.kcsbundle);;ZIP 파일 (*.zip)",
        )
        if not file_path:
            return

        try:
            info = self.settings_bundle_service.export_bundle(file_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "내보내기 실패",
                f"설정 내보내기 중 오류가 발생했습니다.\n\n{e}",
            )
            return

        self.status.set_message(f"설정 내보내기 완료: {info.bundle_path}")
        QMessageBox.information(
            self,
            "설정 내보내기 완료",
            "설정 백업 파일이 생성되었습니다.\n\n"
            f"파일: {info.bundle_path}\n"
            f"연락처: {info.contacts_count}건\n"
            f"그룹: {info.groups_count}건\n"
            f"캠페인: {info.campaigns_count}건\n"
            f"발송리스트: {info.send_lists_count}건\n"
            f"캠페인 이미지 폴더 포함: {'예' if info.has_campaign_assets else '아니오'}\n"
            f"리포트 폴더 포함: {'예' if info.has_reports else '아니오'}\n"
            f"로그 폴더 포함: {'예' if info.has_logs else '아니오'}"
        )

    def import_settings_bundle(self) -> None:
        if self._is_send_busy():
            QMessageBox.information(
                self,
                "안내",
                "발송 중에는 설정 가져오기를 할 수 없습니다.\n발송 종료 후 다시 시도해주세요.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "설정 가져오기",
            str(Path.home() / "Downloads"),
            "카센더 설정 백업 (*.kcsbundle *.zip)",
        )
        if not file_path:
            return

        try:
            info = self.settings_bundle_service.inspect_bundle(file_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "파일 확인 실패",
                f"설정 번들 확인 중 오류가 발생했습니다.\n\n{e}",
            )
            return

        reply = QMessageBox.question(
            self,
            "설정 가져오기",
            "현재 로컬 데이터(DB/캠페인 이미지/리포트/로그)가 가져온 파일로 교체됩니다.\n"
            "DB 파일이 사용 중일 수 있으므로, 프로그램을 먼저 종료한 뒤 오프라인으로 적용합니다.\n"
            "적용이 끝나면 프로그램이 자동으로 다시 실행됩니다.\n\n"
            f"연락처: {info.contacts_count}건\n"
            f"그룹: {info.groups_count}건\n"
            f"캠페인: {info.campaigns_count}건\n"
            f"발송리스트: {info.send_lists_count}건\n"
            f"내보낸 시각: {info.exported_at}\n\n"
            "계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._cleanup_before_close()

        try:
            log_path = schedule_apply_settings_bundle_after_exit(
                bundle_path=file_path,
                wait_pid=os.getpid(),
                relaunch_executable=sys.executable,
                relaunch_args=list(sys.argv[1:]) if getattr(sys, "frozen", False) else list(sys.argv),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "설정 가져오기 실패",
                f"설정 적용 예약 중 오류가 발생했습니다.\n\n{e}",
            )
            return

        self._skip_finalize_pending_update_once = True
        QMessageBox.information(
            self,
            "설정 가져오기 예약 완료",
            "프로그램을 종료한 뒤 설정을 적용합니다.\n"
            "적용 완료 후 프로그램이 자동으로 다시 실행됩니다.\n\n"
            f"적용 로그: {log_path}",
        )
        QApplication.quit()
        sys.exit(0)

    def _restart_application(self) -> None:
        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable] + list(sys.argv[1:])
            else:
                args = [sys.executable] + list(sys.argv)
            subprocess.Popen(args, cwd=os.getcwd(), shell=False)
        except Exception as e:
            QMessageBox.warning(
                self,
                "재시작 안내",
                "자동 재시작에 실패했습니다.\n프로그램을 종료한 뒤 직접 다시 실행해주세요.\n\n"
                f"상세: {e}",
            )
        QApplication.quit()
        sys.exit(0)

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

        self._cleanup_before_close()

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
            from frontend.dialogs.login_dialog import LoginDialog
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

        self._cleanup_before_close()

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
