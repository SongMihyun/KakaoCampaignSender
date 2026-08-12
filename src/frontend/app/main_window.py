# FILE: src/frontend/app/main_window.py
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QCloseEvent, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QStackedWidget,
    QWidget,
)

from app.paths import contacts_db_path
from app.relaunch import relaunch_executable_and_args
from app.version import __display_name__
from backend.core.lifecycle.apply_settings_bundle import schedule_apply_settings_bundle_after_exit
from backend.core.lifecycle.reset_app import schedule_delete_all_local_data
from backend.core.app_settings import get_setting, set_setting
from backend.core.backup_service import backups_dir, create_db_backup
from backend.core.backup_service import delete_backups
from backend.core.support_package import build_support_package
from backend.core.support_package import delete_support_packages
from backend.core.support_sender import open_support_chat_url, send_summary_to_operator
from backend.domains.auth import AuthService
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
from frontend.pages.editor_tools.page import EditorToolsPage
from frontend.pages.groups.page import GroupsPage
from frontend.pages.logs.page import LogsPage
from frontend.pages.sending.page import SendPage


def _dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#12151c"))
    pal.setColor(QPalette.WindowText, QColor("#e8eaed"))
    pal.setColor(QPalette.Base, QColor("#0f1218"))
    pal.setColor(QPalette.AlternateBase, QColor("#191d26"))
    pal.setColor(QPalette.Text, QColor("#e8eaed"))
    pal.setColor(QPalette.Button, QColor("#171b24"))
    pal.setColor(QPalette.ButtonText, QColor("#e8eaed"))
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, QColor("#3b82f6"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor("#14171f"))
    pal.setColor(QPalette.ToolTipText, QColor("#e8eaed"))
    pal.setColor(QPalette.PlaceholderText, QColor("#6d7686"))
    pal.setColor(QPalette.Link, QColor("#3b82f6"))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#5b6270"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#5b6270"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5b6270"))
    return pal


class MainWindow(QMainWindow):
    TITLES = ["대상자 관리", "발송 그룹", "캠페인 설정", "발송", "로그/리포트"]

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(__display_name__)
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setWindowOpacity(0.97)
        self._skip_finalize_pending_update_once = False

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(10)

        self.header = Header()
        self.header.export_settings_requested.connect(self.export_settings_bundle)
        self.header.import_settings_requested.connect(self.import_settings_bundle)
        self.header.environment_changed.connect(self.set_pc_environment)
        self.header.open_logs_requested.connect(self.open_logs_folder)
        self.header.open_backups_requested.connect(self.open_backups_folder)
        self.header.send_support_requested.connect(self.send_support_package)
        self.header.open_support_chat_requested.connect(self.open_support_chat)
        self.header.logout_requested.connect(self.logout)
        self.header.uninstall_requested.connect(self.uninstall_application)
        self.header.home_requested.connect(self._show_sender_mode)
        self.header.editor_requested.connect(self._show_editor_mode)

        self.nav = Navigation()
        self.status = StatusBar()
        self.stack = QStackedWidget()
        self.center_modes = QStackedWidget()

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
        self.header.set_environment(str(get_setting("pc_environment", "public")))
        self._backup_on_lifecycle("startup")
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

        self.editor_page = EditorToolsPage(on_status=self.status.set_message)

        self.stack.addWidget(self.contacts_page)
        self.stack.addWidget(self.groups_page)
        self.stack.addWidget(self.campaign_page)
        self.stack.addWidget(self.send_page)
        self.stack.addWidget(self.logs_page)

        center = QWidget()
        center.setLayout(self.nav.build_layout(self.stack))
        self.center_modes.addWidget(center)
        self.center_modes.addWidget(self.editor_page)

        root_layout.addWidget(self.header)
        root_layout.addWidget(self.center_modes, 1)
        root_layout.addWidget(self.status)

        self.nav.page_changed.connect(self._go_page)
        self._show_sender_mode()
        self._go_page(0)
        self._apply_style()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cleanup_before_close()
        self._clear_auth_session_if_needed()
        self._backup_on_lifecycle("shutdown")
        self._finalize_pending_update()
        super().closeEvent(event)

    def _backup_on_lifecycle(self, reason: str) -> None:
        try:
            create_db_backup(reason=reason)
        except Exception:
            pass

    def _cleanup_before_close(self) -> None:
        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

    def _clear_auth_session_if_needed(self) -> None:
        try:
            auth_service = AuthService()
            if not auth_service.config.persist_session:
                auth_service.clear_session()
        except Exception:
            pass

    def _finalize_pending_update(self) -> None:
        if getattr(self, "_skip_finalize_pending_update_once", False):
            self._skip_finalize_pending_update_once = False
            return
        try:
            from backend.updates.updater import finalize_update_on_app_close

            started = finalize_update_on_app_close()
            if started:
                QMessageBox.information(
                    self,
                    "업데이트 설치",
                    "업데이트 설치를 시작합니다.\n설치가 끝나면 카센더가 다시 실행됩니다.",
                )
        except Exception:
            pass

    def _go_page(self, index: int) -> None:
        self._show_sender_mode(update_subtitle=False)
        self.stack.setCurrentIndex(index)
        title = self.TITLES[index] if 0 <= index < len(self.TITLES) else __display_name__
        self.header.set_subtitle(title)

        try:
            if index == 0 and hasattr(self, "contacts_page") and self.contacts_page:
                try:
                    self.status.set_message(f"대상자 로드: {self.contacts_page.model.rowCount()}건")
                except Exception:
                    pass
            if index == 4 and hasattr(self, "logs_page") and self.logs_page:
                if hasattr(self.logs_page, "refresh"):
                    self.logs_page.refresh()
        except Exception:
            pass

    def _show_sender_mode(self, *, update_subtitle: bool = True) -> None:
        self.center_modes.setCurrentIndex(0)
        self.header.set_mode("home")
        if update_subtitle:
            index = self.stack.currentIndex()
            title = self.TITLES[index] if 0 <= index < len(self.TITLES) else __display_name__
            self.header.set_subtitle(title)

    def _show_editor_mode(self) -> None:
        self.center_modes.setCurrentIndex(1)
        self.header.set_mode("editor")
        self.header.set_subtitle("편집 도구")

    def _apply_style(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setPalette(_dark_palette())
            app.setStyleSheet(APP_STYLESHEET)
        else:
            self.setPalette(_dark_palette())
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

        run_bg(_load_contacts_rows, on_done=_apply)

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

    def set_pc_environment(self, mode: str) -> None:
        mode = "personal" if mode == "personal" else "public"
        set_setting("pc_environment", mode)
        self.header.set_environment(mode)
        if mode == "personal":
            self.status.set_message("사용 환경: 개인 PC | 시작/종료 백업, 최근 7개 유지")
        else:
            self.status.set_message("사용 환경: 공용 PC | 최신 백업 1개만 유지")
        try:
            create_db_backup(reason=f"mode_{mode}", mode=mode)
        except Exception:
            pass

    def open_logs_folder(self) -> None:
        path = Path(contacts_db_path()).parent / "logs"
        path.mkdir(parents=True, exist_ok=True)
        self._open_folder(path)

    def open_backups_folder(self) -> None:
        self._open_folder(backups_dir())

    def _open_folder(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "오류", f"폴더를 열 수 없습니다.\n{path}\n\n{e}")

    def send_support_package(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("오류내용 운영자에게 보내기")
        box.setText("DB에는 대상자 정보가 포함될 수 있습니다.\n\n운영자가 요청한 경우에만 포함하세요.")
        btn_exclude = box.addButton("DB 제외하고 보내기", QMessageBox.AcceptRole)
        btn_include = box.addButton("DB 포함하고 보내기", QMessageBox.DestructiveRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.setDefaultButton(btn_exclude)
        box.exec()

        clicked = box.clickedButton()
        if clicked is None or clicked.text() == "취소":
            return

        include_db = clicked == btn_include
        try:
            result = build_support_package(include_db=include_db)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"오류 신고 패키지 생성 실패\n{e}")
            return

        send_result = send_summary_to_operator(result.summary_message)
        self._open_folder(result.zip_path.parent)

        if send_result.ok:
            QMessageBox.information(
                self,
                "오류 신고 준비 완료",
                "운영자에게 오류 요약을 전송했습니다.\n\n"
                "ZIP 자동 첨부가 실패할 수 있으니 열린 폴더의 ZIP 파일도 운영자에게 전달해 주세요.\n\n"
                f"{result.zip_path}",
            )
        else:
            QMessageBox.warning(
                self,
                "수동 전달 필요",
                "오류 신고 패키지를 만들었지만 운영자 채팅 전송은 실패했습니다.\n\n"
                f"사유: {send_result.reason}\n\n"
                "열린 폴더의 ZIP 파일을 운영자에게 전달해 주세요.\n\n"
                f"{result.zip_path}",
            )

    def open_support_chat(self) -> None:
        result = open_support_chat_url()
        if not result.ok:
            QMessageBox.information(self, "1:1 문의하기", result.reason or "문의 채널이 아직 설정되지 않았습니다.")

    def logout(self) -> None:
        ok = QMessageBox.question(
            self,
            "로그아웃",
            "현재 로그인 세션을 삭제하고 로그인 화면으로 돌아갈까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        try:
            AuthService().logout()
            self._skip_finalize_pending_update_once = True
            exe, args, cwd = relaunch_executable_and_args()
            subprocess.Popen([exe, *args], cwd=cwd or None)
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"로그아웃 실패\n{e}")

    def reset_application(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("초기화 옵션")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("삭제할 항목을 선택하세요. DB/설정 전체 초기화는 앱 종료 후 진행됩니다."))
        chk_logs = QCheckBox("로그 삭제")
        chk_backups = QCheckBox("백업 삭제")
        chk_support = QCheckBox("오류신고파일 삭제")
        chk_logs.setChecked(True)
        lay.addWidget(chk_logs)
        lay.addWidget(chk_backups)
        lay.addWidget(chk_support)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted:
            return

        try:
            if chk_logs.isChecked():
                try:
                    self.logs_service.reset_all()
                except Exception:
                    pass
            if chk_backups.isChecked():
                delete_backups()
            if chk_support.isChecked():
                delete_support_packages()
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
            AuthService().logout()
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
