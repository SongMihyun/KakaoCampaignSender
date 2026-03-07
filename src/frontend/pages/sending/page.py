from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt, QAbstractNativeEventFilter, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QFrame, QListWidget, QListWidgetItem, QTableView, QAbstractItemView,
    QProgressBar, QComboBox, QToolButton, QApplication
)

from app.paths import user_data_dir

from backend.domains.contacts.service import ContactsService
from backend.domains.contacts.dto import ContactUpdateDTO
from backend.domains.groups.repository import GroupsRepo
from backend.domains.campaigns.service import CampaignsService
from backend.domains.send_lists.service import SendListsService
from backend.domains.send_lists.dto import SendListCreateDTO
from backend.domains.sending.service import SendingService
from backend.domains.sending.resolver import (
    resolve_contacts_for_send_list_meta,
    build_recipients_and_snapshot,
)
from backend.domains.reports.writer import SendReportWriter

from frontend.app.app_events import app_events
from frontend.pages.campaigns.preview_dialog import CampaignPreviewDialog

from backend.integrations.kakaotalk.driver import KakaoSenderDriver, KakaoPcDriver
from backend.core.logging.send_run_logger import SendRunLogger


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
            WM_HOTKEY = 0x0312
            if msg.message == WM_HOTKEY:
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

    def register_f11(self, hotkey_id: int = 1001) -> bool:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            MOD_NOREPEAT = 0x4000
            VK_F11 = 0x7A
            self.install()
            ok = bool(user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, VK_F11))
            if ok:
                self._registered_ids.add(hotkey_id)
            return ok
        except Exception:
            return False

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
    ROLE_CONTACT_ID = int(Qt.UserRole) + 101

    def __init__(
        self,
        *,
        contacts_service: ContactsService,
        contacts_store,
        groups_repo: GroupsRepo,
        campaigns_service: CampaignsService,
        send_lists_service: SendListsService,
        sending_service: SendingService,
        send_logs_repo=None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.setObjectName("Page")

        self.contacts_service = contacts_service
        self.contacts_store = contacts_store
        self.groups_repo = groups_repo
        self.campaigns_service = campaigns_service
        self.send_lists_service = send_lists_service
        self.sending_service = sending_service
        self.send_logs_repo = send_logs_repo

        self._on_progress = on_progress or (lambda _: None)
        self._on_status = on_status or (lambda _: None)

        self.sender_driver: Optional[KakaoSenderDriver] = None
        self._worker = None
        self._run_logger: Optional[SendRunLogger] = None
        self._current_sending_title: str = ""

        self._hotkey_mgr: Optional[GlobalHotkeyManager] = None
        self._init_global_hotkey()

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
        self.tbl_preview.setSortingEnabled(True)

        self.preview_model = QStandardItemModel(0, 6, self)
        self.preview_model.setHorizontalHeaderLabels(["No", "사번", "이름", "전화번호", "대리점명", "지사명"])
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
        self.btn_send_stop = QPushButton("중지")
        self.btn_send_stop.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        self.progress.setTextVisible(True)
        self._set_progress_title("")

        action.addWidget(self.btn_send_start)
        action.addWidget(self.btn_send_stop)
        action.addWidget(self.progress, 1)
        root.addLayout(action)

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
        self.btn_send_stop.clicked.connect(self._stop_send)

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

    def _init_global_hotkey(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._hotkey_mgr = GlobalHotkeyManager(app, self._on_global_hotkey)
        self._hotkey_mgr.register_f11(self.HOTKEY_ID_FORCE_STOP)

    def _on_global_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id != self.HOTKEY_ID_FORCE_STOP:
            return
        if self._worker and self._worker.isRunning():
            self._force_stop_send()

    def _force_stop_send(self) -> None:
        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                self._on_status("⚠️ 강제 중지(F11) 실행됨")
        except Exception:
            pass

    def _refresh_priv_label(self) -> None:
        self.lbl_priv.setText("강제 중지: F11  |  발송 중 언제든지 즉시 중지됩니다.")

    def _set_progress_title(self, title: str) -> None:
        self._current_sending_title = (title or "").strip()
        if self._current_sending_title:
            self.progress.setFormat(f"발송중: {self._current_sending_title}  %p%")
        else:
            self.progress.setFormat("%p%")

    def _set_sending_ui(self, sending: bool) -> None:
        self.btn_send_start.setEnabled(not sending)
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

        self.tbl_preview.setEnabled(not sending)

    def _format_title(self, group_name: str, campaign_name: str) -> str:
        group_name = (group_name or "").strip()
        campaign_name = (campaign_name or "").strip()
        return f"{group_name} + {campaign_name}".strip(" +")

    def _refresh_visible_numbers_only(self) -> None:
        for idx in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(idx)
            if not it:
                continue
            data = it.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            title = data.get("title", "")
            it.setText(f"{idx + 1}. {title}")

    def _current_send_list_data(self) -> Optional[dict]:
        it = self.lst_send_lists.currentItem()
        if not it:
            return None
        data = it.data(Qt.UserRole)
        return data if isinstance(data, dict) else None

    def _current_send_list_id(self) -> Optional[int]:
        d = self._current_send_list_data()
        if not d:
            return None
        sid = d.get("send_list_id")
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

    def reload_sources(self) -> None:
        self.cbo_groups.blockSignals(True)
        self.cbo_groups.clear()
        self.cbo_groups.addItem("전체", None)

        groups = self.groups_repo.list_groups()
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
                self.cbo_campaigns.addItem(f"[{c.id}] {c.name}", int(c.id))

        self.cbo_campaigns.setCurrentIndex(0)
        self.cbo_campaigns.blockSignals(False)

        self._on_status("그룹/캠페인 목록 새로고침 완료")

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
            contacts_mem = resolve_contacts_for_send_list_meta(
                contacts_store=self.contacts_store,
                groups_repo=self.groups_repo,
                target_mode=target_mode,
                group_id=key_group_id,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"대상자 로드 실패\n{e}")
            return

        recipients, _snap = build_recipients_and_snapshot(contacts_mem)
        if not recipients:
            QMessageBox.information(self, "안내", "대상자가 없습니다.")
            return

        try:
            send_list_id = self.send_lists_service.create_or_replace(
                SendListCreateDTO(
                    target_mode=target_mode,
                    group_id=key_group_id,
                    group_name=group_name,
                    campaign_id=int(campaign_id),
                    campaign_name=campaign_name,
                )
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송리스트 저장 실패\n{e}")
            return

        self._on_status(f"발송리스트 생성/갱신: id={send_list_id}")
        QMessageBox.information(
            self,
            "완료",
            f"발송리스트 저장 완료\n- ID: {send_list_id}\n- 대상(현재 기준): {len(recipients)}명",
        )

        self.reload_send_lists(select_send_list_id=int(send_list_id))

    def reload_send_lists(self, *, select_send_list_id: Optional[int] = None) -> None:
        self.lst_send_lists.blockSignals(True)
        self.lst_send_lists.clear()

        try:
            rows = self.send_lists_service.list_send_lists()
        except Exception as e:
            self.lst_send_lists.blockSignals(False)
            QMessageBox.critical(self, "오류", f"발송리스트 로드 실패\n{e}")
            return

        if not rows:
            it = QListWidgetItem("(저장된 발송리스트 없음)")
            it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.lst_send_lists.addItem(it)

            self.lst_send_lists.blockSignals(False)
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            return

        selected_row_to_set = 0

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
            item.setData(Qt.UserRole, {
                "send_list_id": send_list_id,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "group_name": group_name,
                "title": title,
                "target_mode": target_mode,
                "group_id": group_id,
            })
            self.lst_send_lists.addItem(item)

            if select_send_list_id is not None and send_list_id == int(select_send_list_id):
                selected_row_to_set = idx - 1

        self.lst_send_lists.blockSignals(False)
        self.lst_send_lists.setCurrentRow(selected_row_to_set)
        self._on_status("발송리스트 새로고침 완료")

    def _on_send_list_selected(self, row: int) -> None:
        it = self.lst_send_lists.item(row)
        if not it:
            return

        data = it.data(Qt.UserRole)
        if not isinstance(data, dict):
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            return

        send_list_id = data.get("send_list_id")
        title = str(data.get("title", "") or "")
        if send_list_id is None:
            return

        try:
            meta = self.send_lists_service.get_meta(int(send_list_id))
        except Exception:
            meta = None

        if not meta:
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("발송리스트 메타 로드 실패")
            return

        try:
            contacts_mem = resolve_contacts_for_send_list_meta(
                contacts_store=self.contacts_store,
                groups_repo=self.groups_repo,
                target_mode=str(getattr(meta, "target_mode", "") or ""),
                group_id=getattr(meta, "group_id", None),
            )
        except Exception as e:
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("대상자 로드 실패")
            QMessageBox.critical(self, "오류", f"대상자 로드 실패\n{e}")
            return

        self.preview_model.setRowCount(0)

        shown = 0
        for m in (contacts_mem or []):
            raw_name = str(getattr(m, "name", "") or "")
            name = raw_name.strip().replace("\u200b", "").replace("\ufeff", "")
            if not name:
                continue

            shown += 1
            cid_int = int(getattr(m, "id", 0) or 0)

            it_no = QStandardItem(str(shown))
            it_no.setData(cid_int, self.ROLE_CONTACT_ID)

            self.preview_model.appendRow([
                it_no,
                QStandardItem(str(getattr(m, "emp_id", "") or "")),
                QStandardItem(name),
                QStandardItem(str(getattr(m, "phone", "") or "")),
                QStandardItem(str(getattr(m, "agency", "") or "")),
                QStandardItem(str(getattr(m, "branch", "") or "")),
            ])

        self.lbl_footer.setText(f"대상(현재 기준): {shown}명 / 발송리스트: {title}")

    def _on_preview_double_clicked(self, index: QModelIndex) -> None:
        try:
            if not index.isValid():
                return

            row = index.row()
            it_no = self.preview_model.item(row, 0)
            if it_no is None:
                return

            contact_id = it_no.data(self.ROLE_CONTACT_ID)
            try:
                contact_id = int(contact_id) if contact_id is not None else 0
            except Exception:
                contact_id = 0

            if contact_id <= 0:
                QMessageBox.information(self, "안내", "원본 대상자 ID(contact_id)를 확인할 수 없습니다.")
                return

            preset = None
            try:
                row_obj = self.contacts_service.repo.get_by_id(int(contact_id))
                if row_obj:
                    preset = type("Tmp", (), {
                        "emp_id": getattr(row_obj, "emp_id", "") or "",
                        "name": getattr(row_obj, "name", "") or "",
                        "phone": getattr(row_obj, "phone", "") or "",
                        "agency": getattr(row_obj, "agency", "") or "",
                        "branch": getattr(row_obj, "branch", "") or "",
                    })()
            except Exception:
                preset = None

            if preset is None:
                emp = self.preview_model.item(row, 1).text() if self.preview_model.item(row, 1) else ""
                name = self.preview_model.item(row, 2).text() if self.preview_model.item(row, 2) else ""
                phone = self.preview_model.item(row, 3).text() if self.preview_model.item(row, 3) else ""
                agency = self.preview_model.item(row, 4).text() if self.preview_model.item(row, 4) else ""
                branch = self.preview_model.item(row, 5).text() if self.preview_model.item(row, 5) else ""
                preset = type("Tmp", (), {
                    "emp_id": emp or "",
                    "name": name or "",
                    "phone": phone or "",
                    "agency": agency or "",
                    "branch": branch or "",
                })()

            from frontend.pages.contacts.dialog import ContactDialog

            dlg = ContactDialog("대상자 수정", preset=preset, parent=self)
            ok = bool(dlg.exec())
            if not ok:
                return

            form = dlg.get_contact()

            new_emp_id = (form.get("emp_id") or "").strip()
            new_name = (form.get("name") or "").strip()
            new_phone = (form.get("phone") or "").strip()
            new_agency = (form.get("agency") or "").strip()
            new_branch = (form.get("branch") or "").strip()

            if not new_name:
                QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
                return

            try:
                self.contacts_service.update_contact(
                    ContactUpdateDTO(
                        row_id=int(contact_id),
                        emp_id=new_emp_id,
                        name=new_name,
                        phone=new_phone,
                        agency=new_agency,
                        branch=new_branch,
                    )
                )
            except ValueError as e:
                QMessageBox.warning(self, "중복 오류", str(e))
                return
            except Exception as e:
                QMessageBox.critical(self, "오류", f"대상자 저장 실패\n{e}")
                return

            self._sync_after_contact_change(contact_id=int(contact_id))

        except Exception as e:
            QMessageBox.critical(self, "오류", f"대상자 수정 처리 실패\n{e}")

    def _sync_after_contact_change(self, *, contact_id: int) -> None:
        try:
            if hasattr(self.contacts_store, "reload"):
                self.contacts_store.reload()  # type: ignore[attr-defined]
            elif hasattr(self.contacts_store, "refresh"):
                self.contacts_store.refresh()  # type: ignore[attr-defined]
        except Exception:
            pass

        cur_sid = self._current_send_list_id()
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._refresh_current_preview()

        try:
            app_events.contacts_changed.emit()
        except Exception:
            pass
        try:
            app_events.groups_changed.emit()
        except Exception:
            pass

        self._on_status("대상자 수정 반영됨 (참조형: 즉시 최신 반영)")
        self._refresh_current_preview()

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
            self, "삭제 확인",
            f"발송리스트를 삭제하시겠습니까?\n- {title}",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self.send_lists_service.delete_send_list(int(send_list_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패\n{e}")
            return

        self._on_status(f"발송리스트 삭제: id={send_list_id}")
        self.reload_send_lists()

    def _save_send_list_order(self) -> None:
        ordered_ids: list[int] = []
        for i in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(i)
            if not it:
                continue
            data = it.data(Qt.UserRole)
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
            self.send_lists_service.update_orders(ordered_ids)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"순서 저장 실패\n{e}")
            return

        self._on_status("발송리스트 순서 저장 완료")
        cur_sid = self._current_send_list_id()
        self.reload_send_lists(select_send_list_id=cur_sid)

    def _on_send_list_double_clicked(self, it: QListWidgetItem) -> None:
        data = it.data(Qt.UserRole)
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

    def _start_send_all_lists(self) -> None:
        self._run_logger = None
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "안내", "이미 발송 중입니다.")
            return

        hwnd = self._pick_best_kakao_target_handle()
        if hwnd is None:
            QMessageBox.information(self, "안내", "카카오톡 창이 없습니다.\n카카오톡 실행/로그인 후 다시 시도하세요.")
            return

        self._refresh_visible_numbers_only()

        send_list_rows: list[dict] = []
        for i in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(i)
            if not it:
                continue
            if not (it.flags() & Qt.ItemIsEnabled):
                continue

            data = it.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue

            send_list_rows.append(data)

        try:
            jobs = self.sending_service.build_jobs(send_list_rows)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송 준비(리스트 로드) 실패\n{e}")
            return

        if not jobs:
            QMessageBox.information(self, "안내", "발송할 발송리스트가 없습니다.")
            return

        filtered = [j for j in jobs if j.campaign_items]
        if not filtered:
            QMessageBox.information(self, "안내", "발송 가능한 발송리스트가 없습니다. (캠페인 내용 없음)")
            return

        total_targets = sum(len(j.recipients) for j in filtered)

        ok = QMessageBox.question(
            self, "발송 시작",
            f"발송리스트 {len(filtered)}개를 위에서부터 순차 발송합니다.\n"
            f"- 총 대상: {total_targets}명\n\n"
            f"계속 진행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            speed_mode = str(self.cbo_speed.currentData() or "normal")
        except Exception:
            speed_mode = "normal"

        self.sender_driver = KakaoPcDriver(
            int(hwnd),
            speed_mode=speed_mode,
            block_input=False,
            use_alt_tab_confirm=False,
            alt_tab_max_steps=0,
        )

        self.progress.setValue(0)
        self._set_progress_title(f"1/{len(filtered)} {filtered[0].title}")
        self._set_sending_ui(True)

        run_logger = SendRunLogger.new_run(prefix="send_run")
        self._run_logger = run_logger
        self._on_status(
            f"발송 시작(카카오톡 자동화) | 속도: {speed_mode.upper()} | 강제중지: F11 | 로그: {run_logger.path_str()}"
        )

        run_id = time.strftime("%Y%m%d_%H%M%S")
        report_writer = SendReportWriter(base_dir=user_data_dir(), run_id=run_id)
        report_writer.set_meta(total_lists=len(filtered), total_targets=total_targets)
        self._on_status(f"리포트 파일 생성: {str(report_writer.path)}")

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
        self._worker.progress.connect(self.progress.setValue)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished_ok.connect(self._on_send_finished)
        self._worker.start()

    def _on_worker_list_changed(self, title: str, idx: int, total: int) -> None:
        self._set_progress_title(f"{idx}/{total} {title}")
        self.progress.setValue(0)

    def _stop_send(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return
        self._worker.request_stop()
        self._on_status("중지 요청됨")

    def _on_send_finished(self, list_done: int, success: int, fail: int) -> None:
        self._set_sending_ui(False)
        self._set_progress_title("")
        self.progress.setValue(100 if (success + fail) > 0 else 0)

        log_path = ""
        try:
            if self._run_logger:
                log_path = self._run_logger.path_str()
        except Exception:
            log_path = ""

        QMessageBox.information(
            self, "발송 종료",
            f"발송 종료\n- 완료 리스트: {list_done}개\n- 성공: {success}\n- 실패: {fail}"
            + (f"\n\n로그 파일:\n{log_path}" if log_path else "")
        )

        self._on_status(
            f"발송 종료 | 리스트 {list_done}개 완료 | 성공 {success} / 실패 {fail}"
            + (f" | 로그: {log_path}" if log_path else "")
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

    def cleanup(self) -> None:
        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                self._worker.wait(1500)
        except Exception:
            pass

        try:
            if self._hotkey_mgr:
                self._hotkey_mgr.unregister_all()
                self._hotkey_mgr = None
        except Exception:
            pass

        self._run_logger = None

    def _on_campaigns_changed(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        cur = self.cbo_campaigns.currentData()
        self.reload_sources()

        if cur is not None:
            for i in range(self.cbo_campaigns.count()):
                if self.cbo_campaigns.itemData(i) == cur:
                    self.cbo_campaigns.setCurrentIndex(i)
                    break

        self._on_status("캠페인 목록 자동 갱신됨")

    def _on_contacts_changed(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        cur_sid = self._current_send_list_id()
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._refresh_current_preview()

    def _on_groups_changed(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        cur_sid = self._current_send_list_id()
        self.reload_sources()
        self.reload_send_lists(select_send_list_id=cur_sid)
        self._refresh_current_preview()


__all__ = ["SendPage"]