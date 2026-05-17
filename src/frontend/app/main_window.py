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
from app.relaunch import relaunch_executable_and_args
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
from backend.domains.scheduled_sends.repository import ScheduledSendsRepo
from backend.domains.scheduled_sends.service import ScheduledSendsService
from backend.domains.sending.job_builder import SendJobBuilder
from backend.domains.sending.service import SendingService
from backend.domains.sending.worker import MultiSendWorker
from backend.domains.settings_bundle.service import SettingsBundleService
from backend.stores.contacts_store import ContactsStore

from frontend.theme import APP_STYLESHEET
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
        self.scheduled_sends_repo = ScheduledSendsRepo(db_path)

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
        self.scheduled_sends_service = ScheduledSendsService(
            repo=self.scheduled_sends_repo,
        )

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
            scheduled_sends_service=self.scheduled_sends_service,
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
        self.setStyleSheet(APP_STYLESHEET)

    def _on_contacts_changed_global(self) -> None:
        from frontend.utils.worker import run_bg
        from frontend.app.app_events import app_events

        def _load_contacts_rows() -> list[dict]:
            try:
                return self.contacts_repo.list_all()
            except Exception:
                return self.contacts_repo.search_contacts("")

        def _apply(rows: list[dict]) -> None:
            try:
                self.contacts_store.load_rows(rows)
            except Exception:
                try:
                    self.contacts_store.clear()
                except Exception:
                    pass

            try:
                if hasattr(self, "groups_page") and self.groups_page:
                    self.groups_page.reload_groups()
            except Exception:
                pass

            try:
                if hasattr(self, "send_page") and self.send_page:
                    self.send_page.reload_sources()
                    self.send_page.reload_send_lists()
            except Exception:
                pass

            try:
                app_events.groups_changed.emit()  # type: ignore[attr-defined]
            except Exception:
                pass

        run_bg(self, _load_contacts_rows, done=_apply)

    def export_settings_bundle(self) -> None:
        default_name = f"kakao_sender_settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kcsbundle"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "설정 내보내기",
            str(Path.home() / default_name),
            "카센더 설정 번들 (*.kcsbundle *.zip);;ZIP Files (*.zip)",
        )
        if not path:
            return

        try:
            info = self.settings_bundle_service.export_bundle(path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 내보내기 실패\n{e}")
            return

        QMessageBox.information(
            self,
            "완료",
            "설정보내기가 완료되었습니다.\n"
            "다른 PC에서 로그인 후 [설정 가져오기]로 이 파일을 선택하면\n"
            "대상자·그룹·캠페인·발송리스트가 덮어씌워집니다.\n\n"
            f"파일: {info.bundle_path}\n"
            f"연락처 {info.contacts_count}명 · 그룹 {info.groups_count}개 · "
            f"캠페인 {info.campaigns_count}개 · 발송리스트 {info.send_lists_count}개",
        )

    def import_settings_bundle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "설정 가져오기",
            str(Path.home()),
            "카센더 설정 번들 (*.kcsbundle *.zip);;ZIP Files (*.zip)",
        )
        if not path:
            return

        try:
            info = self.settings_bundle_service.inspect_bundle(path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 파일을 읽을 수 없습니다.\n{e}")
            return

        reply = QMessageBox.question(
            self,
            "설정 가져오기",
            "아래 내용으로 이 PC의 로컬 데이터를 덮어씁니다.\n"
            "(연락처·그룹·캠페인·발송리스트·캠페인 이미지 등)\n\n"
            f"보낸 시각: {info.exported_at or '-'}\n"
            f"연락처 {info.contacts_count}명\n"
            f"그룹 {info.groups_count}개\n"
            f"캠페인 {info.campaigns_count}개\n"
            f"발송리스트 {info.send_lists_count}개\n\n"
            "적용을 위해 앱이 종료된 뒤 자동으로 다시 실행됩니다.\n"
            "계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            relaunch_exe, relaunch_args, relaunch_cwd = relaunch_executable_and_args()
            schedule_apply_settings_bundle_after_exit(
                bundle_path=path,
                wait_pid=os.getpid(),
                relaunch_executable=relaunch_exe,
                relaunch_args=relaunch_args,
                relaunch_working_dir=relaunch_cwd,
            )
            self._skip_finalize_pending_update_once = True
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 가져오기 예약 실패\n{e}")

    def logout(self) -> None:
        QMessageBox.information(self, "로그아웃", "로그아웃 기능은 준비 중입니다.")

    def reset_application(self) -> None:
        reply = QMessageBox.warning(
            self,
            "초기화 확인",
            "앱의 로컬 데이터(DB/로그/설정)를 모두 삭제하고 종료합니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            schedule_delete_all_local_data()
            self._skip_finalize_pending_update_once = True
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"초기화 예약 실패\n{e}")

    def uninstall_application(self) -> None:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        ps1 = root / "uninstall.ps1"
        if not ps1.exists():
            QMessageBox.information(
                self,
                "안내",
                f"삭제 스크립트를 찾을 수 없습니다.\n{ps1}",
            )
            return

        reply = QMessageBox.warning(
            self,
            "프로그램 삭제",
            "프로그램 제거를 시작합니다.\n진행 중 앱이 종료될 수 있습니다.\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            flags = 0
            try:
                flags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
            except Exception:
                flags = 0

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
            self._skip_finalize_pending_update_once = True
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실행 실패\n{e}")
