# (파일 경로는 질문에 나온 두 번째 코드 블록 파일 기준)
from __future__ import annotations

import sys
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
from app.data.send_logs_repo import SendLogsRepo   # ✅ 추가

from app.system.reset_app import schedule_delete_all_local_data

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
        self.setWindowTitle("Kakao Campaign Sender (Local)")
        self.resize(1180, 760)

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.header = Header()
        # ✅ Header 메뉴 액션 연결
        self.header.logout_requested.connect(self.logout)
        self.header.uninstall_requested.connect(self.uninstall_application)

        self.nav = Navigation()
        self.status = StatusBar()

        self.stack = QStackedWidget()

        db_path = contacts_db_path()

        self.contacts_repo = ContactsRepo(db_path)
        self.groups_repo = GroupsRepo(db_path)
        self.campaigns_repo = CampaignsRepo(db_path)
        self.send_lists_repo = SendListsRepo(db_path)

        # ✅ 로그 Repo 추가
        self.send_logs_repo = SendLogsRepo(db_path)
        self.send_logs_repo.ensure_tables()

        self.contacts_page = ContactsPage(repo=self.contacts_repo, on_status=self.status.set_message)
        self.groups_page = GroupsPage(repo=self.groups_repo, on_status=self.status.set_message)
        self.campaign_page = CampaignPage(repo=self.campaigns_repo, on_status=self.status.set_message)

        self.send_page = SendPage(
            contacts_repo=self.contacts_repo,
            groups_repo=self.groups_repo,
            campaigns_repo=self.campaigns_repo,
            send_lists_repo=self.send_lists_repo,
            send_logs_repo=self.send_logs_repo,
            on_progress=self.status.set_progress,
            on_status=self.status.set_message,
        )

        # ✅ LogsPage는 repo 주입형으로 생성
        self.logs_page = LogsPage(
            logs_repo=self.send_logs_repo,
            campaigns_repo=self.campaigns_repo,
            on_reset_all=self.reset_application,  # ✅ 전체 리셋 버튼이 MainWindow.reset_application 호출
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
        # 1) 발송 워커/드라이버 정리
        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

        # 2) 업데이트가 예약되어 있으면 종료 직전에 설치 실행
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

        # ✅ 로그 페이지 진입 시 자동 새로고침(운영 UX 개선)
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
        """)

    # (기존 reset_application은 유지 가능: 메뉴/별도 버튼에서 쓰려면 남겨두세요)
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

        # 현재는 계정/세션 개념이 없으므로 최소 동작: 홈으로 이동
        self._go_page(0)
        QMessageBox.information(self, "완료", "로그아웃 되었습니다.")

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

        # 1) 발송 워커/드라이버 정리
        try:
            if hasattr(self, "send_page") and self.send_page:
                self.send_page.cleanup()
        except Exception:
            pass

        # 2) 언인스톨러 실행
        try:
            from app.system.uninstall import find_uninstaller, launch_uninstaller

            uninst = find_uninstaller()
            if not uninst:
                QMessageBox.warning(
                    self,
                    "언인스톨러 없음",
                    "언인스톨러를 찾지 못했습니다.\n"
                    "Windows '앱 및 기능'에서 KakaoCampaignSender를 제거해주세요.",
                )
                return

            launch_uninstaller(uninst)

        except Exception as e:
            QMessageBox.critical(self, "제거 실행 실패", f"제거 실행 중 오류:\n{e}")
            return

        # 3) 앱 종료(언인스톨 진행을 위해)
        QApplication.quit()
        sys.exit(0)