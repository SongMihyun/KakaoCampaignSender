# FILE: src/frontend/pages/sending/page.py
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt, QAbstractNativeEventFilter, QModelIndex, QTimer, QDateTime
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QTableView,
    QAbstractItemView,
    QProgressBar,
    QComboBox,
    QToolButton,
    QApplication,
    QDateTimeEdit,
)

from app.paths import user_data_dir

from backend.domains.contacts.service import ContactsService
from backend.domains.campaigns.service import CampaignsService
from backend.domains.reports.writer import SendReportWriter
from backend.domains.send_lists.dto import SendListCreateDTO
from backend.domains.sending.service import SendingService

from frontend.app.app_events import app_events
from frontend.pages.campaigns.preview_dialog import CampaignPreviewDialog
from frontend.utils.contact_edit import edit_contact_by_id

from backend.core.logging.send_run_logger import SendRunLogger
from backend.integrations.kakaotalk.driver import KakaoPcDriver, KakaoSenderDriver


class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey: Callable[[int], None]) -> None:
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):  # type: ignore[override]
        try:
            if eventType != "windows_generic_MSG":
                return False, 0

            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            wm_hotkey = 0x0312
            if msg.message == wm_hotkey:
                hotkey_id = int(msg.wParam)
                try:
                    self._on_hotkey(hotkey_id)
                except Exception:
                    pass
                return True, 0
        except Exception:
            pass

        return False, 0


class GlobalHotkeyManager:
    def __init__(self, app: QApplication, on_hotkey: Callable[[int], None]) -> None:
        self._app = app
        self._filter = GlobalHotkeyFilter(on_hotkey)
        self._registered_ids: set[int] = set()
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._app.installNativeEventFilter(self._filter)
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        try:
            self._app.removeNativeEventFilter(self._filter)
        except Exception:
            pass
        self._installed = False

    def register_hotkey(self, hotkey_id: int, vk_code: int) -> bool:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            mod_norepeat = 0x4000

            self.install()
            ok = bool(user32.RegisterHotKey(None, hotkey_id, mod_norepeat, int(vk_code)))
            if ok:
                self._registered_ids.add(hotkey_id)
            return ok
        except Exception:
            return False

    def register_f11(self, hotkey_id: int = 1001) -> bool:
        return self.register_hotkey(hotkey_id, 0x7A)

    def register_f9(self, hotkey_id: int = 1002) -> bool:
        return self.register_hotkey(hotkey_id, 0x78)

    def unregister_all(self) -> None:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            for hid in list(self._registered_ids):
                try:
                    user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass
            self._registered_ids.clear()
        finally:
            self.uninstall()


class SendPage(QWidget):
    HOTKEY_ID_FORCE_STOP = 1001
    HOTKEY_ID_PAUSE_TOGGLE = 1002
    ROLE_CONTACT_ID = int(Qt.UserRole) + 101

    def __init__(
        self,
        *,
        contacts_service: ContactsService,
        contacts_store,
        campaigns_service: CampaignsService,
        sending_service: SendingService,
        scheduled_sends_service=None,
        send_logs_repo=None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.setObjectName("Page")

        self.contacts_service = contacts_service
        self.contacts_store = contacts_store
        self.campaigns_service = campaigns_service
        self.sending_service = sending_service
        self.scheduled_sends_service = scheduled_sends_service
        self.send_logs_repo = send_logs_repo

        self._on_progress = on_progress or (lambda _: None)
        self._on_status = on_status or (lambda _: None)

        self.sender_driver: Optional[KakaoSenderDriver] = None
        self._worker = None
        self._run_logger: Optional[SendRunLogger] = None
        self._current_sending_title: str = ""
        self._is_pause_ui: bool = False
        self._active_scheduled_send_id: Optional[int] = None
        self._latest_schedule_id: Optional[int] = None
        self._exit_after_scheduled_send: bool = False

        self._hotkey_mgr: Optional[GlobalHotkeyManager] = None
        self._init_global_hotkey()

        self._preview_cache: dict[int, tuple[list[dict], str]] = {}
        self._send_lists_reload_pending_select_id: Optional[int] = None
        self._last_preview_send_list_id: Optional[int] = None

        self._sources_reload_timer = QTimer(self)
        self._sources_reload_timer.setSingleShot(True)
        self._sources_reload_timer.timeout.connect(self.reload_sources)

        self._send_lists_reload_timer = QTimer(self)
        self._send_lists_reload_timer.setSingleShot(True)
        self._send_lists_reload_timer.timeout.connect(self._flush_reload_send_lists)

        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.timeout.connect(self._refresh_current_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        root.addLayout(header_row)

        header_left = QVBoxLayout()
        header_left.setSpacing(6)

        title = QLabel("발송")
        title.setObjectName("PageTitle")
        desc = QLabel("발송리스트(그룹+캠페인)를 생성/관리하고, 리스트를 순차 발송합니다.")
        desc.setObjectName("PageDesc")

        header_left.addWidget(title)
        header_left.addWidget(desc)

        self.lbl_priv = QLabel("")
        self.lbl_priv.setStyleSheet("color:#b45309; font-weight:600;")
        header_left.addWidget(self.lbl_priv)
        self._refresh_priv_label()

        self.lbl_pause_badge = QLabel("일시정지됨 · 카카오톡 사용 가능 · 다음 대상은 검색창부터 재개")
        self.lbl_pause_badge.setVisible(False)
        self.lbl_pause_badge.setStyleSheet(
            "background:#b91c1c; color:white; font-weight:700; "
            "border:1px solid #991b1b; border-radius:14px; "
            "padding:6px 12px;"
        )
        header_left.addWidget(self.lbl_pause_badge, 0, Qt.AlignLeft)

        header_row.addLayout(header_left, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(8)
        header_right.setAlignment(Qt.AlignTop | Qt.AlignRight)

        lbl_speed = QLabel("속도")
        lbl_speed.setStyleSheet("color:#6b7280; font-weight:600;")

        self.cbo_speed = QComboBox()
        self.cbo_speed.setMinimumWidth(140)
        self.cbo_speed.addItem("SLOW(안정)", "slow")
        self.cbo_speed.addItem("NORMAL(기본)", "normal")
        self.cbo_speed.addItem("FAST(빠름)", "fast")
        self.cbo_speed.setCurrentIndex(1)

        header_right.addWidget(lbl_speed)
        header_right.addWidget(self.cbo_speed)
        header_row.addLayout(header_right)

        main = QHBoxLayout()
        main.setSpacing(12)
        root.addLayout(main, 1)

        left_card = QFrame()
        left_card.setObjectName("Card")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        lv.addWidget(QLabel("발송리스트 생성"))

        form = QHBoxLayout()
        form.setSpacing(8)

        form.addWidget(QLabel("그룹"))
        self.cbo_groups = QComboBox()
        form.addWidget(self.cbo_groups, 2)

        form.addWidget(QLabel("캠페인"))
        self.cbo_campaigns = QComboBox()
        form.addWidget(self.cbo_campaigns, 3)

        lv.addLayout(form)

        form_btns = QHBoxLayout()
        self.btn_create_send_list = QPushButton("발송리스트 생성")
        self.btn_reload_sources = QPushButton("목록 새로고침")
        form_btns.addWidget(self.btn_create_send_list)
        form_btns.addWidget(self.btn_reload_sources)
        form_btns.addStretch(1)
        lv.addLayout(form_btns)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lv.addWidget(sep)

        lv.addWidget(QLabel("발송리스트 관리"))

        self.lst_send_lists = QListWidget()
        self.lst_send_lists.setMinimumWidth(380)
        self.lst_send_lists.setDragDropMode(QListWidget.InternalMove)
        self.lst_send_lists.setDefaultDropAction(Qt.MoveAction)
        lv.addWidget(self.lst_send_lists, 1)

        btn_row = QHBoxLayout()
        self.btn_refresh_lists = QPushButton("새로고침")

        self.btn_move_up = QToolButton()
        self.btn_move_up.setText("▲")

        self.btn_move_down = QToolButton()
        self.btn_move_down.setText("▼")

        self.btn_delete_list = QPushButton("삭제")
        self.btn_save_order = QPushButton("순서 저장")

        btn_row.addWidget(self.btn_refresh_lists)
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        btn_row.addWidget(self.btn_delete_list)
        btn_row.addWidget(self.btn_save_order)
        btn_row.addStretch(1)
        lv.addLayout(btn_row)

        main.addWidget(left_card, 3)
        left_card.setMaximumWidth(520)

        right_card = QFrame()
        right_card.setObjectName("Card")
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(8)

        rv.addWidget(QLabel("발송 대상 리스트(미리보기)"))

        self.tbl_preview = QTableView()
        self.tbl_preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_preview.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setSortingEnabled(False)

        self.preview_model = QStandardItemModel(0, 6, self)
        self.preview_model.setHorizontalHeaderLabels(
            ["No", "사번", "이름", "전화번호", "대리점명", "지사명"]
        )
        self.tbl_preview.setModel(self.preview_model)

        self.tbl_preview.setColumnWidth(0, 50)
        self.tbl_preview.setColumnWidth(1, 95)
        self.tbl_preview.setColumnWidth(2, 80)
        self.tbl_preview.setColumnWidth(3, 130)
        self.tbl_preview.setColumnWidth(4, 130)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)

        rv.addWidget(self.tbl_preview, 1)

        self.lbl_footer = QLabel("선택된 발송리스트가 없습니다.")
        self.lbl_footer.setStyleSheet("color:#6b7280;")
        rv.addWidget(self.lbl_footer)

        main.addWidget(right_card, 9)

        action = QHBoxLayout()

        self.btn_send_start = QPushButton("발송 시작")
        self.btn_send_pause = QPushButton("일시정지(F9)")
        self.btn_send_pause.setEnabled(False)

        self.btn_send_stop = QPushButton("중지")
        self.btn_send_stop.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        self.progress.setTextVisible(True)
        self._set_progress_title("")

        action.addWidget(self.btn_send_start)
        action.addWidget(self.btn_send_pause)
        action.addWidget(self.btn_send_stop)
        action.addWidget(self.progress, 1)
        root.addLayout(action)

        schedule_row = QHBoxLayout()
        schedule_row.setSpacing(8)

        schedule_row.addWidget(QLabel("예약 시각"))

        self.dte_schedule = QDateTimeEdit()
        self.dte_schedule.setCalendarPopup(True)
        self.dte_schedule.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dte_schedule.setDateTime(QDateTime.currentDateTime().addSecs(600))

        self.btn_schedule_save = QPushButton("예약 저장")
        self.btn_schedule_cancel = QPushButton("예약 취소")
        self.lbl_schedule_status = QLabel("예약 없음")
        self.lbl_schedule_status.setStyleSheet("color:#6b7280;")

        schedule_row.addWidget(self.dte_schedule)
        schedule_row.addWidget(self.btn_schedule_save)
        schedule_row.addWidget(self.btn_schedule_cancel)
        schedule_row.addWidget(self.lbl_schedule_status, 1)
        root.addLayout(schedule_row)

        self.btn_reload_sources.clicked.connect(self.reload_sources)
        self.btn_create_send_list.clicked.connect(self._create_send_list)

        self.btn_refresh_lists.clicked.connect(self.reload_send_lists)
        self.btn_delete_list.clicked.connect(self._delete_selected_send_list)
        self.btn_save_order.clicked.connect(self._save_send_list_order)

        self.btn_move_up.clicked.connect(self._move_selected_send_list_up)
        self.btn_move_down.clicked.connect(self._move_selected_send_list_down)

        self.lst_send_lists.currentRowChanged.connect(self._on_send_list_selected)
        self.lst_send_lists.itemDoubleClicked.connect(self._on_send_list_double_clicked)

        self.btn_send_start.clicked.connect(self._start_send_all_lists)
        self.btn_send_pause.clicked.connect(self._toggle_pause_send)
        self.btn_send_stop.clicked.connect(self._stop_send)
        self.btn_schedule_save.clicked.connect(self._create_scheduled_send)
        self.btn_schedule_cancel.clicked.connect(self._cancel_latest_schedule)

        self.tbl_preview.doubleClicked.connect(self._on_preview_double_clicked)

        try:
            app_events.campaigns_changed.connect(self._on_campaigns_changed)
        except Exception:
            pass
        try:
            app_events.contacts_changed.connect(self._on_contacts_changed)
        except Exception:
            pass
        try:
            app_events.groups_changed.connect(self._on_groups_changed)
        except Exception:
            pass

        self.reload_sources()
        self.reload_send_lists()
        self.refresh_schedule_status()

    def set_exit_after_scheduled_send(self, enabled: bool) -> None:
        self._exit_after_scheduled_send = bool(enabled)

    def refresh_schedule_status(self) -> None:
        if self.scheduled_sends_service is None:
            self._latest_schedule_id = None
            self.lbl_schedule_status.setText("예약 기능 비활성")
            return

        try:
            row = self.scheduled_sends_service.get_latest_actionable()
        except Exception as e:
            self._latest_schedule_id = None
            self.lbl_schedule_status.setText(f"예약 조회 실패: {e}")
            return

        if not row:
            self._latest_schedule_id = None
            self.lbl_schedule_status.setText("예약 없음")
            return

        self._latest_schedule_id = int(row.id)
        self.lbl_schedule_status.setText(
            f"최근 예약 #{row.id} | {row.status} | {row.planned_at}"
        )

    def _collect_enabled_send_list_rows(self) -> list[dict]:
        send_list_rows: list[dict] = []
        for i in range(self.lst_send_lists.count()):
            item = self.lst_send_lists.item(i)
            if not item:
                continue
            if not (item.flags() & Qt.ItemIsEnabled):
                continue

            data = item.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            send_list_rows.append(data)
        return send_list_rows

    def _resolve_self_launch(self) -> tuple[str, list[str], str]:
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
            work_dir = os.path.dirname(sys.executable) or os.getcwd()
            return exe_path, [], work_dir

        exe_path = sys.executable
        script_args = [sys.argv[0]]
        work_dir = os.getcwd()
        return exe_path, script_args, work_dir

    def _create_scheduled_send(self) -> None:
        if self.scheduled_sends_service is None:
            QMessageBox.warning(self, "안내", "예약발송 서비스가 연결되지 않았습니다.")
            return

        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "안내", "발송 중에는 예약을 저장할 수 없습니다.")
            return

        send_list_rows = self._collect_enabled_send_list_rows()
        if not send_list_rows:
            QMessageBox.information(self, "안내", "예약할 발송리스트가 없습니다.")
            return

        planned_at = self.dte_schedule.dateTime().toPython()
        if planned_at <= datetime.now():
            QMessageBox.warning(self, "안내", "현재 시각 이후로 예약해주세요.")
            return

        try:
            speed_mode = str(self.cbo_speed.currentData() or "normal")
        except Exception:
            speed_mode = "normal"

        exe_path, base_args, work_dir = self._resolve_self_launch()

        try:
            schedule_id = self.scheduled_sends_service.create_schedule(
                planned_at=planned_at,
                speed_mode=speed_mode,
                send_list_rows=send_list_rows,
                executable_path=exe_path,
                arguments=base_args,
                working_dir=work_dir,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 저장 실패\n{e}")
            return

        self._latest_schedule_id = int(schedule_id)
        self.lbl_schedule_status.setText(
            f"예약됨 #{schedule_id} / {planned_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self._on_status(f"예약발송 등록 완료: #{schedule_id}")

    def _cancel_latest_schedule(self) -> None:
        if self.scheduled_sends_service is None:
            return
        schedule_id = self._latest_schedule_id
        if not schedule_id:
            QMessageBox.information(self, "안내", "취소할 예약이 없습니다.")
            return

        row = None
        try:
            row = self.scheduled_sends_service.get_schedule(int(schedule_id))
        except Exception:
            row = None

        if row is None or row.status not in ("PENDING", "FAILED"):
            QMessageBox.information(self, "안내", "취소 가능한 예약이 없습니다.")
            self.refresh_schedule_status()
            return

        reply = QMessageBox.question(
            self,
            "예약 취소",
            f"예약 #{row.id} ({row.planned_at}) 을 취소하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.scheduled_sends_service.cancel_schedule(int(schedule_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 취소 실패\n{e}")
            return

        self._on_status(f"예약 취소 완료: #{schedule_id}")
        self.refresh_schedule_status()

    def _init_global_hotkey(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._hotkey_mgr = GlobalHotkeyManager(app, self._on_global_hotkey)
        self._hotkey_mgr.register_f11(self.HOTKEY_ID_FORCE_STOP)
        self._hotkey_mgr.register_f9(self.HOTKEY_ID_PAUSE_TOGGLE)

    def _on_global_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == self.HOTKEY_ID_FORCE_STOP:
            if self._worker and self._worker.isRunning():
                self._force_stop_send()
            return

        if hotkey_id == self.HOTKEY_ID_PAUSE_TOGGLE:
            if self._worker and self._worker.isRunning():
                self._toggle_pause_send()
            return

    def _force_stop_send(self) -> None:
        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                self._on_status("⚠️ 강제 중지(F11) 실행됨")
        except Exception:
            pass

    def _refresh_priv_label(self) -> None:
        self.lbl_priv.setText("F9: 현재 열린 대화 발송 후 안전 정지/재개  |  F11: 강제 중지  |  일시정지됨 표시 후 카카오톡 사용 가능")

    def _refresh_progress_format(self) -> None:
        if not self._current_sending_title:
            self.progress.setFormat("%p%")
            return

        prefix = "일시정지" if self._is_pause_ui else "발송중"
        self.progress.setFormat(f"{prefix}: {self._current_sending_title}  %p%")

    def _set_progress_title(self, title: str) -> None:
        self._current_sending_title = (title or "").strip()
        self._refresh_progress_format()

    def _refresh_pause_badge(self) -> None:
        try:
            self.lbl_pause_badge.setVisible(bool(self._is_pause_ui))
        except Exception:
            pass

    def _set_pause_ui(self, paused: bool) -> None:
        self._is_pause_ui = bool(paused)
        self.btn_send_pause.setText("재개(F9)" if self._is_pause_ui else "일시정지(F9)")
        self.btn_send_pause.setStyleSheet(
            "font-weight:700; color:#b45309;" if self._is_pause_ui else ""
        )
        self._refresh_pause_badge()
        self._refresh_progress_format()

    def _set_sending_ui(self, sending: bool) -> None:
        if not sending:
            self._is_pause_ui = False
            self._refresh_pause_badge()

        self.btn_send_start.setEnabled(not sending)
        self.btn_send_pause.setEnabled(sending)
        self.btn_send_stop.setEnabled(sending)

        self.btn_create_send_list.setEnabled(not sending)
        self.btn_reload_sources.setEnabled(not sending)

        self.btn_refresh_lists.setEnabled(not sending)
        self.btn_delete_list.setEnabled(not sending)
        self.btn_save_order.setEnabled(not sending)
        self.lst_send_lists.setEnabled(not sending)

        self.cbo_groups.setEnabled(not sending)
        self.cbo_campaigns.setEnabled(not sending)
        self.cbo_speed.setEnabled(not sending)
        self.dte_schedule.setEnabled(not sending)
        self.btn_schedule_save.setEnabled(not sending)
        self.btn_schedule_cancel.setEnabled(not sending)

        self.tbl_preview.setEnabled(not sending)

    def _format_title(self, group_name: str, campaign_name: str) -> str:
        group_name = (group_name or "").strip()
        campaign_name = (campaign_name or "").strip()
        return f"{group_name} + {campaign_name}".strip(" +")

    def _refresh_visible_numbers_only(self) -> None:
        for idx in range(self.lst_send_lists.count()):
            item = self.lst_send_lists.item(idx)
            if not item:
                continue
            data = item.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            title = data.get("title", "")
            item.setText(f"{idx + 1}. {title}")

    def _current_send_list_data(self) -> Optional[dict]:
        item = self.lst_send_lists.currentItem()
        if not item:
            return None
        data = item.data(Qt.UserRole)
        return data if isinstance(data, dict) else None

    def _current_send_list_id(self) -> Optional[int]:
        data = self._current_send_list_data()
        if not data:
            return None
        sid = data.get("send_list_id")
        try:
            return int(sid) if sid is not None else None
        except Exception:
            return None

    def _pick_best_kakao_target_handle(self) -> Optional[int]:
        targets = KakaoPcDriver.list_targets()
        if not targets:
            return None

        best = None
        best_score = -1
        for t in targets:
            title = str(getattr(t, "title", "") or "")
            hwnd = int(getattr(t, "handle", 0) or 0)
            if hwnd <= 0:
                continue

            score = 0
            if "카카오톡" in title:
                score += 10
            if "kakaotalk" in title.lower():
                score += 9
            if len(title.strip()) >= 3:
                score += 1

            if score > best_score:
                best_score = score
                best = hwnd

        return best

    def _clear_preview_cache(self) -> None:
        self._preview_cache.clear()

    def _invalidate_preview_cache(self, send_list_id: Optional[int] = None) -> None:
        if send_list_id is None:
            self._preview_cache.clear()
            return
        self._preview_cache.pop(int(send_list_id), None)

    def _schedule_reload_sources(self, delay_ms: int = 120) -> None:
        self._sources_reload_timer.start(max(0, int(delay_ms)))

    def _schedule_refresh_current_preview(self, delay_ms: int = 80) -> None:
        self._preview_refresh_timer.start(max(0, int(delay_ms)))

    def reload_sources(self) -> None:
        self.cbo_groups.blockSignals(True)
        self.cbo_groups.clear()
        self.cbo_groups.addItem("전체", None)

        groups = self.sending_service.list_groups()
        for g in (groups or []):
            self.cbo_groups.addItem(str(getattr(g, "name", "")), int(getattr(g, "id")))

        self.cbo_groups.setCurrentIndex(0)
        self.cbo_groups.blockSignals(False)

        self.cbo_campaigns.blockSignals(True)
        self.cbo_campaigns.clear()

        campaigns = self.campaigns_service.list_campaigns()
        if not campaigns:
            self.cbo_campaigns.addItem("(캠페인 없음)", None)
        else:
            for c in campaigns:
                mode = str(getattr(c, "send_mode", "clipboard") or "clipboard")
                mode_tag = " | 묶음" if mode == "multi_attach" else ""
                self.cbo_campaigns.addItem(f"[{c.id}] {c.name}{mode_tag}", int(c.id))

        self.cbo_campaigns.setCurrentIndex(0)
        self.cbo_campaigns.blockSignals(False)

        self._on_status("그룹/캠페인 목록 새로고침 완료")

    def reload_send_lists(self, *, select_send_list_id: Optional[int] = None) -> None:
        self._send_lists_reload_pending_select_id = select_send_list_id
        self._send_lists_reload_timer.start(120)

    def _flush_reload_send_lists(self) -> None:
        current_selected_id = self._current_send_list_id()

        self.lst_send_lists.blockSignals(True)
        self.lst_send_lists.clear()

        try:
            rows = self.sending_service.list_send_lists()
        except Exception as e:
            self.lst_send_lists.blockSignals(False)
            QMessageBox.critical(self, "오류", f"발송리스트 로드 실패\n{e}")
            return

        if not rows:
            item = QListWidgetItem("(저장된 발송리스트 없음)")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.lst_send_lists.addItem(item)

            self.lst_send_lists.blockSignals(False)
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            self._last_preview_send_list_id = None
            self._send_lists_reload_pending_select_id = None
            return

        selected_row_to_set = 0
        select_send_list_id = self._send_lists_reload_pending_select_id
        if select_send_list_id is None:
            select_send_list_id = current_selected_id

        for idx, r in enumerate(rows, start=1):
            send_list_id = int(getattr(r, "id"))
            group_name = str(getattr(r, "group_name", "") or "")
            campaign_name = str(getattr(r, "campaign_name", "") or "")
            campaign_id = int(getattr(r, "campaign_id"))

            target_mode = str(getattr(r, "target_mode", "") or "")
            group_id = getattr(r, "group_id", None)
            try:
                group_id = int(group_id) if group_id is not None else None
            except Exception:
                group_id = None

            title = self._format_title(group_name, campaign_name)
            visible = f"{idx}. {title}"

            item = QListWidgetItem(visible)
            item.setData(
                Qt.UserRole,
                {
                    "send_list_id": send_list_id,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "group_name": group_name,
                    "title": title,
                    "target_mode": target_mode,
                    "group_id": group_id,
                },
            )
            self.lst_send_lists.addItem(item)

            if select_send_list_id is not None and send_list_id == int(select_send_list_id):
                selected_row_to_set = idx - 1

        self.lst_send_lists.blockSignals(False)
        self.lst_send_lists.setCurrentRow(selected_row_to_set)
        self._on_status("발송리스트 새로고침 완료")
        self._send_lists_reload_pending_select_id = None

    def _create_send_list(self) -> None:
        group_id = self.cbo_groups.currentData()
        group_name = str(self.cbo_groups.currentText() or "").strip()

        campaign_id = self.cbo_campaigns.currentData()
        if campaign_id is None:
            QMessageBox.information(self, "안내", "캠페인을 선택하세요.")
            return
        campaign_name = str(self.cbo_campaigns.currentText() or "").strip()

        if group_id is None:
            target_mode = "ALL"
            key_group_id = None
            group_name = "전체"
        else:
            target_mode = "GROUP"
            key_group_id = int(group_id)

        try:
            send_list_id, target_count = self.sending_service.create_or_replace_send_list(
                SendListCreateDTO(
                    target_mode=target_mode,
                    group_id=key_group_id,
                    group_name=group_name,
                    campaign_id=int(campaign_id),
                    campaign_name=campaign_name,
                )
            )
        except ValueError as e:
            QMessageBox.information(self, "안내", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송리스트 저장 실패\n{e}")
            return

        self._invalidate_preview_cache(int(send_list_id))
        self._on_status(f"발송리스트 생성/갱신: id={send_list_id}")
        QMessageBox.information(
            self,
            "완료",
            f"발송리스트 저장 완료\n- ID: {send_list_id}\n- 대상(현재 기준): {target_count}명",
        )

        self.reload_send_lists(select_send_list_id=int(send_list_id))

    def _on_send_list_selected(self, row: int) -> None:
        item = self.lst_send_lists.item(row)
        if not item:
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            self._last_preview_send_list_id = None
            return

        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            self._last_preview_send_list_id = None
            return

        send_list_id = data.get("send_list_id")
        if send_list_id is None:
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            self._last_preview_send_list_id = None
            return

        send_list_id = int(send_list_id)
        self._last_preview_send_list_id = send_list_id
        cached = self._preview_cache.get(send_list_id)

        if cached is None:
            try:
                rows, title = self.sending_service.build_preview_rows(send_list_id)
            except Exception as e:
                self.preview_model.setRowCount(0)
                self.lbl_footer.setText("대상자 로드 실패")
                QMessageBox.critical(self, "오류", f"대상자 로드 실패\n{e}")
                return
            self._preview_cache[send_list_id] = (rows, title)
        else:
            rows, title = cached

        self._render_preview_rows(rows)
        self.lbl_footer.setText(f"대상(현재 기준): {len(rows)}명 / 발송리스트: {title}")

    def _make_preview_row_items(self, row_data: dict) -> list[QStandardItem]:
        item_no = QStandardItem(str(row_data["no"]))
        item_no.setData(int(row_data["contact_id"]), self.ROLE_CONTACT_ID)

        row_items = [
            item_no,
            QStandardItem(str(row_data["emp_id"] or "")),
            QStandardItem(str(row_data["name"] or "")),
            QStandardItem(str(row_data["phone"] or "")),
            QStandardItem(str(row_data["agency"] or "")),
            QStandardItem(str(row_data["branch"] or "")),
        ]
        for item in row_items:
            item.setEditable(False)
        return row_items

    def _render_preview_rows(self, rows: list[dict]) -> None:
        current_index = self.tbl_preview.currentIndex()
        current_contact_id: Optional[int] = None

        if current_index.isValid():
            item_no = self.preview_model.item(current_index.row(), 0)
            if item_no is not None:
                try:
                    raw_contact_id = item_no.data(self.ROLE_CONTACT_ID)
                    current_contact_id = int(raw_contact_id) if raw_contact_id is not None else None
                except Exception:
                    current_contact_id = None

        self.tbl_preview.setUpdatesEnabled(False)
        self.tbl_preview.setSortingEnabled(False)

        try:
            self.preview_model.removeRows(0, self.preview_model.rowCount())

            built_rows = [self._make_preview_row_items(row_data) for row_data in rows]
            for row_items in built_rows:
                self.preview_model.appendRow(row_items)

            if current_contact_id is not None:
                for row_idx in range(self.preview_model.rowCount()):
                    item_no = self.preview_model.item(row_idx, 0)
                    if item_no is None:
                        continue
                    try:
                        row_contact_id = item_no.data(self.ROLE_CONTACT_ID)
                        row_contact_id = int(row_contact_id) if row_contact_id is not None else None
                    except Exception:
                        row_contact_id = None

                    if row_contact_id == current_contact_id:
                        self.tbl_preview.selectRow(row_idx)
                        break
        finally:
            self.tbl_preview.setSortingEnabled(False)
            self.tbl_preview.setUpdatesEnabled(True)

    def _on_preview_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return

        row = index.row()
        item_no = self.preview_model.item(row, 0)
        if item_no is None:
            return

        contact_id = item_no.data(self.ROLE_CONTACT_ID)
        try:
            contact_id = int(contact_id) if contact_id is not None else 0
        except Exception:
            contact_id = 0

        fallback_preset = self._build_contact_preset_from_preview_row(row)

        ok = edit_contact_by_id(
            self,
            contacts_service=self.contacts_service,
            contact_id=contact_id,
            fallback_preset=fallback_preset,
            emit_event=True,
        )
        if not ok:
            return

        self._sync_after_contact_change()
        self._on_status("대상자 수정 반영됨 (참조형: 즉시 최신 반영)")

    def _build_contact_preset_from_preview_row(self, row: int):
        return {
            "emp_id": self.preview_model.item(row, 1).text() if self.preview_model.item(row, 1) else "",
            "name": self.preview_model.item(row, 2).text() if self.preview_model.item(row, 2) else "",
            "phone": self.preview_model.item(row, 3).text() if self.preview_model.item(row, 3) else "",
            "agency": self.preview_model.item(row, 4).text() if self.preview_model.item(row, 4) else "",
            "branch": self.preview_model.item(row, 5).text() if self.preview_model.item(row, 5) else "",
        }

    def _sync_after_contact_change(self) -> None:
        cur_sid = self._current_send_list_id()
        self._invalidate_preview_cache(cur_sid)
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._schedule_refresh_current_preview()

        try:
            app_events.groups_changed.emit()
        except Exception:
            pass

    def _refresh_current_preview(self) -> None:
        row = self.lst_send_lists.currentRow()
        if row < 0:
            return
        self._on_send_list_selected(row)

    def _delete_selected_send_list(self) -> None:
        data = self._current_send_list_data()
        if not data:
            QMessageBox.information(self, "안내", "삭제할 발송리스트를 선택하세요.")
            return

        send_list_id = data.get("send_list_id")
        if send_list_id is None:
            return

        title = data.get("title", "")

        ok = QMessageBox.question(
            self,
            "삭제 확인",
            f"발송리스트를 삭제하시겠습니까?\n- {title}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self.sending_service.delete_send_list(int(send_list_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패\n{e}")
            return

        self._invalidate_preview_cache(int(send_list_id))
        self._on_status(f"발송리스트 삭제: id={send_list_id}")
        self.reload_send_lists()

    def _save_send_list_order(self) -> None:
        ordered_ids: list[int] = []
        for i in range(self.lst_send_lists.count()):
            item = self.lst_send_lists.item(i)
            if not item:
                continue
            data = item.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            sid = data.get("send_list_id")
            if sid is None:
                continue
            ordered_ids.append(int(sid))

        if not ordered_ids:
            QMessageBox.information(self, "안내", "저장할 발송리스트가 없습니다.")
            return

        try:
            self.sending_service.update_send_list_orders(ordered_ids)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"순서 저장 실패\n{e}")
            return

        self._clear_preview_cache()
        self._on_status("발송리스트 순서 저장 완료")
        cur_sid = self._current_send_list_id()
        self.reload_send_lists(select_send_list_id=cur_sid)

    def _on_send_list_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return

        campaign_id = data.get("campaign_id")
        title = data.get("title", "")

        if campaign_id is None:
            QMessageBox.information(self, "안내", "캠페인 정보가 없습니다.")
            return

        try:
            items = self.campaigns_service.get_campaign_items(int(campaign_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"캠페인 미리보기 로드 실패\n{e}")
            return

        dlg = CampaignPreviewDialog(campaign_title=title, items=items, parent=self)
        dlg.exec()

    def _start_send_jobs(
        self,
        *,
        jobs: list,
        speed_mode: str,
        confirm: bool,
        scheduled_send_id: int | None = None,
    ) -> None:
        self._run_logger = None

        if self._worker and self._worker.isRunning():
            raise RuntimeError("이미 발송 중입니다.")

        hwnd = self._pick_best_kakao_target_handle()
        if hwnd is None:
            raise RuntimeError("카카오톡 창이 없습니다.\n카카오톡 실행/로그인 후 다시 시도하세요.")

        if not jobs:
            raise RuntimeError("발송할 발송리스트가 없습니다.")

        filtered = [j for j in jobs if j.campaign_items]
        if not filtered:
            raise RuntimeError("발송 가능한 발송리스트가 없습니다. (캠페인 내용 없음)")

        total_targets = sum(len(j.recipients) for j in filtered)

        if confirm:
            ok = QMessageBox.question(
                self,
                "발송 시작",
                f"발송리스트 {len(filtered)}개를 위에서부터 순차 발송합니다.\n"
                f"- 총 대상: {total_targets}명\n\n"
                f"계속 진행하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ok != QMessageBox.Yes:
                return

        self._active_scheduled_send_id = scheduled_send_id

        self.sender_driver = KakaoPcDriver(
            int(hwnd),
            speed_mode=speed_mode,
            block_input=False,
            use_alt_tab_confirm=False,
            alt_tab_max_steps=0,
        )

        self.progress.setValue(0)
        self._set_pause_ui(False)
        self._set_progress_title(f"1/{len(filtered)} {filtered[0].title}")
        self._set_sending_ui(True)

        run_logger = SendRunLogger.new_run(prefix="send_run")
        self._run_logger = run_logger

        run_id = time.strftime("%Y%m%d_%H%M%S")
        report_writer = SendReportWriter(base_dir=user_data_dir(), run_id=run_id)
        report_writer.set_meta(total_lists=len(filtered), total_targets=total_targets)

        self._worker = self.sending_service.create_worker(
            driver=self.sender_driver,
            jobs=filtered,
            parent=self,
            delay_ms=500,
            max_retry=2,
            retry_sleep_ms=250,
            run_logger=run_logger,
            report_writer=report_writer,
        )
        self._worker.list_changed.connect(self._on_worker_list_changed)
        self._worker.pause_changed.connect(self._on_worker_pause_changed)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished_ok.connect(self._on_send_finished)
        self._worker.start()

    def _start_send_all_lists(self) -> None:
        self._refresh_visible_numbers_only()

        send_list_rows = self._collect_enabled_send_list_rows()

        try:
            jobs = self.sending_service.build_jobs(send_list_rows)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송 준비(리스트 로드) 실패\n{e}")
            return

        try:
            speed_mode = str(self.cbo_speed.currentData() or "normal")
        except Exception:
            speed_mode = "normal"

        try:
            self._start_send_jobs(
                jobs=jobs,
                speed_mode=speed_mode,
                confirm=True,
                scheduled_send_id=None,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def start_scheduled_send(self, schedule_id: int) -> bool:
        if self.scheduled_sends_service is None:
            self._on_status("예약발송 서비스가 연결되지 않았습니다.")
            return False

        try:
            locked = self.scheduled_sends_service.mark_running_if_pending(schedule_id)
            if not locked:
                self._on_status(f"예약 #{schedule_id} 는 이미 처리되었거나 실행 중입니다.")
                self.refresh_schedule_status()
                return False

            schedule = self.scheduled_sends_service.get_schedule(schedule_id)
            if schedule is None:
                raise RuntimeError("예약 정보를 찾을 수 없습니다.")

            send_list_rows = self.scheduled_sends_service.get_snapshot_rows(schedule_id)
            jobs = self.sending_service.build_jobs(send_list_rows)

            self._start_send_jobs(
                jobs=jobs,
                speed_mode=str(schedule.speed_mode or "normal"),
                confirm=False,
                scheduled_send_id=int(schedule_id),
            )
            self._on_status(f"예약발송 시작: #{schedule_id}")
            self.refresh_schedule_status()
            return True

        except Exception as e:
            try:
                self.scheduled_sends_service.mark_failed(schedule_id, str(e))
            except Exception:
                pass
            self._on_status(f"예약발송 오류: {e}")
            self.refresh_schedule_status()
            return False

    def _toggle_pause_send(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return

        try:
            toggle_fn = getattr(self._worker, "toggle_pause", None)
            if callable(toggle_fn):
                toggle_fn()
            elif self._worker.is_paused():
                self._worker.request_resume()
            else:
                self._worker.request_pause()
        except Exception:
            pass

    def _stop_send(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return
        self._worker.request_stop()
        self._set_pause_ui(False)
        if self._active_scheduled_send_id and self.scheduled_sends_service:
            try:
                self.scheduled_sends_service.mark_failed(self._active_scheduled_send_id, "사용자 중지")
            except Exception:
                pass
        self._on_status("중지 요청됨(F11 또는 버튼)")

    def _on_send_finished(self, list_done: int, success: int, fail: int) -> None:
        self._set_pause_ui(False)
        self._set_sending_ui(False)
        self._set_progress_title("")
        self.progress.setValue(100 if (success + fail) > 0 else 0)

        active_schedule_id = self._active_scheduled_send_id
        self._active_scheduled_send_id = None

        log_path = ""
        try:
            if self._run_logger:
                log_path = self._run_logger.path_str()
        except Exception:
            log_path = ""

        if active_schedule_id and self.scheduled_sends_service:
            try:
                self.scheduled_sends_service.mark_done(active_schedule_id)
            except Exception as e:
                self._on_status(f"예약 상태 완료 반영 실패: {e}")

        self.refresh_schedule_status()

        summary = (
            f"발송 종료 | 리스트 {list_done}개 완료 | 성공 {success} / 실패 {fail}"
            + (f" | 로그: {log_path}" if log_path else "")
        )
        self._on_status(summary)

        if active_schedule_id:
            if self._exit_after_scheduled_send:
                QTimer.singleShot(1500, QApplication.quit)
            return

        QMessageBox.information(
            self,
            "발송 종료",
            f"발송 종료\n- 완료 리스트: {list_done}개\n- 성공: {success}\n- 실패: {fail}"
            + (f"\n\n로그 파일:\n{log_path}" if log_path else ""),
        )

    def _move_selected_send_list_up(self) -> None:
        row = self.lst_send_lists.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)

    def _move_selected_send_list_down(self) -> None:
        row = self.lst_send_lists.currentRow()
        if row < 0 or row >= (self.lst_send_lists.count() - 1):
            return
        self._swap_rows(row, row + 1)

    def _swap_rows(self, a: int, b: int) -> None:
        if a == b:
            return
        if a < 0 or b < 0:
            return
        if a >= self.lst_send_lists.count() or b >= self.lst_send_lists.count():
            return

        item_a = self.lst_send_lists.takeItem(a)
        item_b = self.lst_send_lists.takeItem(b if b < a else b - 1)

        self.lst_send_lists.insertItem(a, item_b)
        self.lst_send_lists.insertItem(b, item_a)

        self.lst_send_lists.setCurrentRow(b)
        self._refresh_visible_numbers_only()

    def _on_campaigns_changed(self) -> None:
        cur_sid = self._current_send_list_id()
        self._clear_preview_cache()
        self._schedule_reload_sources()
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._schedule_refresh_current_preview()

    def _on_contacts_changed(self) -> None:
        cur_sid = self._current_send_list_id()
        self._invalidate_preview_cache(cur_sid)
        self._schedule_refresh_current_preview()

    def _on_groups_changed(self) -> None:
        cur_sid = self._current_send_list_id()
        self._clear_preview_cache()
        self._schedule_reload_sources()
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._schedule_refresh_current_preview()


    def is_sending_active(self) -> bool:
        try:
            return bool(self._worker and self._worker.isRunning())
        except Exception:
            return False

    def cleanup(self) -> None:
        try:
            self._sources_reload_timer.stop()
            self._send_lists_reload_timer.stop()
            self._preview_refresh_timer.stop()
        except Exception:
            pass

        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                try:
                    self._worker.wait(1500)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self._hotkey_mgr:
                self._hotkey_mgr.unregister_all()
        except Exception:
            pass