# FILE: src/frontend/pages/contacts/page.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, List

from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QKeyEvent, QAction
from PySide6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QLineEdit,
    QTableView, QMessageBox, QDialog, QAbstractItemView, QMenu, QToolButton
)

from backend.stores.contacts_store import ContactsStore
from frontend.pages.contacts.table_model import ContactsTableModel, Contact
from frontend.pages.contacts.dialog import ContactDialog
from frontend.pages.contacts.paste_import_dialog import PasteImportDialog
from backend.domains.contacts.service import ContactsService
from backend.domains.contacts.dto import ContactCreateDTO
from backend.integrations.excel.contacts_importer import (
    import_contacts_file,
    import_contacts_text,
    is_supported_contact_import_file,
)
from backend.integrations.excel.contacts_exporter import export_contacts_xlsx, create_template_xlsx
from frontend.pages.contacts.import_preview_dialog import ImportPreviewDialog

from frontend.widgets.checkable_header import CheckableHeader
from frontend.widgets.contacts_sort_proxy import ContactsSortProxyModel
from frontend.utils.worker import run_bg
from frontend.utils.contact_edit import edit_contact_by_id
from backend.integrations.windows.win_file_picker import pick_open_file, pick_save_file, Filter
from frontend.app.app_events import app_events


class ContactsPage(QWidget):
    ACTION_BTN_W = 104
    ACTION_BTN_H = 34

    def __init__(
        self,
        service: ContactsService,
        contacts_store: ContactsStore,
        on_status: Optional[Callable[[str], None]] = None
    ) -> None:
        super().__init__()
        self.setObjectName("Page")
        self._on_status = on_status or (lambda _: None)
        self.service = service
        self.store = contacts_store
        self._suppress_contacts_event = False
        self._busy = False

        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("대상자 관리")
        title.setObjectName("PageTitle")

        desc = QLabel("로컬 SQLite 저장/조회 기반 대상자 관리 (파일/붙여넣기/드래그앤드롭 Import + 체크 삭제/엑셀 Export).")
        desc.setObjectName("PageDesc")

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("이름/사번/전화/대리점/지사 검색")
        btn_search_clear = QPushButton("초기화")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(btn_search_clear)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_add = QPushButton("신규 추가")
        self.btn_edit = QPushButton("수정")
        self.btn_delete = QPushButton("삭제")
        self.btn_reload = QPushButton("새로고침")
        self.btn_bulk_manage = self._create_bulk_manage_button()

        for btn in [self.btn_add, self.btn_edit, self.btn_delete, self.btn_reload]:
            self._apply_action_button_style(btn)
            btn_row.addWidget(btn)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_bulk_manage)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)

        self.model = ContactsTableModel(rows=[])
        self.proxy = ContactsSortProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)

        self.table.setModel(self.proxy)
        self.table.verticalHeader().setVisible(False)

        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 56)

        self.table.clicked.connect(self._on_table_clicked)
        self.table.doubleClicked.connect(self._on_contact_double_clicked)

        hdr = CheckableHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(hdr)

        hdr.setSortIndicatorShown(True)
        hdr.setSectionsClickable(True)
        hdr.setStretchLastSection(True)
        hdr.toggled.connect(self._toggle_all_checked)

        self.model.dataChanged.connect(lambda *_: self._sync_header_checkbox())
        self.model.layoutChanged.connect(lambda *_: self._sync_header_checkbox())

        self.table.sortByColumn(1, Qt.AscendingOrder)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addLayout(search_row)
        layout.addLayout(btn_row)
        layout.addWidget(self.table, 1)

        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        btn_search_clear.clicked.connect(self._clear_search)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete_checked)
        self.btn_reload.clicked.connect(self.reload)

        app_events.contacts_changed.connect(self._on_contacts_changed)  # type: ignore[arg-type]

        self.installEventFilter(self)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)

        self.reload()
        QTimer.singleShot(0, self._sync_header_checkbox)

    def _apply_action_button_style(self, btn: QPushButton) -> None:
        btn.setFixedSize(self.ACTION_BTN_W, self.ACTION_BTN_H)

    def _create_bulk_manage_button(self) -> QToolButton:
        btn = QToolButton(self)
        btn.setText("일괄 관리")
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn.setFixedSize(self.ACTION_BTN_W, self.ACTION_BTN_H)
        btn.setMenu(self._build_bulk_menu(btn))
        return btn

    def _build_bulk_menu(self, parent) -> QMenu:
        menu = QMenu(parent)

        act_import_all = QAction("전체 파일 가져오기", menu)
        act_import_excel = QAction("엑셀 파일 가져오기", menu)
        act_import_word = QAction("워드 파일 가져오기", menu)
        act_import_text = QAction("메모장/CSV 파일 가져오기", menu)
        act_paste = QAction("붙여넣기 업로드", menu)
        act_template = QAction("샘플 서식 다운로드", menu)
        act_export = QAction("엑셀 내보내기", menu)

        act_import_all.triggered.connect(lambda: self._pick_import_file("all"))
        act_import_excel.triggered.connect(lambda: self._pick_import_file("excel"))
        act_import_word.triggered.connect(lambda: self._pick_import_file("word"))
        act_import_text.triggered.connect(lambda: self._pick_import_file("text"))
        act_paste.triggered.connect(self._open_paste_dialog)
        act_template.triggered.connect(self._download_template)
        act_export.triggered.connect(self._export_excel)

        menu.addAction(act_import_all)
        menu.addSeparator()
        menu.addAction(act_import_excel)
        menu.addAction(act_import_word)
        menu.addAction(act_import_text)
        menu.addSeparator()
        menu.addAction(act_paste)
        menu.addAction(act_template)
        menu.addAction(act_export)
        return menu

    def eventFilter(self, watched, event):
        if watched in {self, self.table, self.table.viewport()}:
            if event.type() == QEvent.KeyPress:
                key_event = event if isinstance(event, QKeyEvent) else None
                if key_event and self._is_direct_paste_event(key_event):
                    self._paste_from_clipboard()
                    return True

            if event.type() in {QEvent.DragEnter, QEvent.DragMove}:
                if self._has_supported_dropped_files(event):
                    event.acceptProposedAction()
                    return True

            if event.type() == QEvent.Drop:
                if self._handle_file_drop(event):
                    return True

        return super().eventFilter(watched, event)

    def _is_direct_paste_event(self, event: QKeyEvent) -> bool:
        if self._busy:
            return False
        if event.key() != Qt.Key_V:
            return False
        if event.modifiers() != Qt.ControlModifier:
            return False
        if self.search.hasFocus():
            return False
        return True

    def _has_supported_dropped_files(self, event) -> bool:
        if self._busy:
            return False
        mime = event.mimeData()
        if not mime or not mime.hasUrls():
            return False

        for url in mime.urls():
            if url.isLocalFile() and is_supported_contact_import_file(url.toLocalFile()):
                return True
        return False

    def _handle_file_drop(self, event) -> bool:
        if not self._has_supported_dropped_files(event):
            return False

        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and is_supported_contact_import_file(url.toLocalFile())
        ]
        if not files:
            return False

        path = files[0]
        event.acceptProposedAction()

        if len(files) > 1:
            QMessageBox.information(
                self,
                "안내",
                f"여러 파일이 드롭되었습니다. 첫 번째 지원 파일만 처리합니다.\n\n{Path(path).name}"
            )

        self._import_file_from_path(path, source_label="드래그앤드롭")
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for b in [
            self.btn_add, self.btn_edit, self.btn_delete, self.btn_reload, self.btn_bulk_manage
        ]:
            b.setEnabled(not busy)

    def _show_bg_error(self, tb: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "오류", tb)

    def _on_contacts_changed(self) -> None:
        if self._suppress_contacts_event:
            return

        current_filter = self.search.text()
        checked = self.model.checked_ids()

        self.reload()

        if self.search.text() != current_filter:
            self.search.setText(current_filter)

        self.model.set_checked_ids(checked)
        self._sync_header_checkbox()
        self._on_status("대상자 자동 갱신 완료")

    def reload(self) -> None:
        rows = self.store.list_all()
        contacts = [
            Contact(
                id=m.id,
                emp_id=(m.emp_id or ""),
                name=m.name,
                phone=m.phone or "",
                agency=m.agency or "",
                branch=m.branch or ""
            )
            for m in rows
        ]
        self.model.reset_rows(contacts)
        self._on_status(f"대상자 로드: {len(contacts)}건")
        self._sync_header_checkbox()

    def _clear_search(self) -> None:
        self.search.setText("")
        self._on_status("검색 조건 초기화")
        self._sync_header_checkbox()

    def _selected_source_rows(self) -> list[int]:
        rows: List[int] = []
        sel = self.table.selectionModel()
        if not sel:
            return rows
        for idx in sel.selectedRows():
            src = self.proxy.mapToSource(idx)
            rows.append(src.row())
        return sorted(set(rows))

    def _add(self) -> None:
        dlg = ContactDialog("대상자 추가", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_contact()
        name = (data.get("name") or "").strip()
        emp_id = (data.get("emp_id") or "").strip()
        phone = (data.get("phone") or "").strip()
        agency = (data.get("agency") or "").strip()
        branch = (data.get("branch") or "").strip()

        if not name:
            QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
            return

        try:
            self.service.create_contact(
                ContactCreateDTO(
                    emp_id=emp_id,
                    name=name,
                    phone=phone,
                    agency=agency,
                    branch=branch,
                )
            )
        except ValueError as e:
            QMessageBox.warning(self, "중복 오류", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")
            return

        self.reload()

        self._suppress_contacts_event = True
        try:
            app_events.contacts_changed.emit()
        finally:
            self._suppress_contacts_event = False

        if self.search.text().strip():
            self.search.setText("")
        self._sync_header_checkbox()
        self._on_status(f"추가 완료: {name} ({emp_id if emp_id else '사번없음'})")

    def _edit(self) -> None:
        rows = self._selected_source_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "안내", "수정은 1건만 선택하세요.")
            return

        row = rows[0]
        preset = self.model.contact_at(row)

        ok = edit_contact_by_id(
            self,
            contacts_service=self.service,
            contact_id=int(preset.id),
        )
        if not ok:
            return

        emp_disp = (preset.emp_id or "").strip() or "(사번없음)"
        self._on_status(f"수정 완료: {preset.name} ({emp_disp})")

    def _delete_checked(self) -> None:
        ids = self.model.checked_ids()
        if not ids:
            QMessageBox.information(self, "안내", "삭제할 항목을 체크하세요.")
            return

        ok = QMessageBox.question(
            self,
            "삭제 확인",
            f"{len(ids)}건을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self.service.delete_contacts(ids)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패:\n{e}")
            return

        self.reload()

        self._suppress_contacts_event = True
        try:
            app_events.contacts_changed.emit()
        finally:
            self._suppress_contacts_event = False

        self._on_status(f"삭제 완료: {len(ids)}건")

    def _pick_import_file(self, mode: str = "all") -> None:
        try:
            if mode == "excel":
                filters = [
                    Filter("Excel Files", "*.xlsx;*.xlsm"),
                    Filter("All Files", "*.*"),
                ]
                default_ext = "xlsx"
            elif mode == "word":
                filters = [
                    Filter("Word Files", "*.docx"),
                    Filter("All Files", "*.*"),
                ]
                default_ext = "docx"
            elif mode == "text":
                filters = [
                    Filter("Text Files", "*.txt;*.csv;*.tsv"),
                    Filter("All Files", "*.*"),
                ]
                default_ext = "txt"
            else:
                filters = [
                    Filter("지원 파일", "*.xlsx;*.xlsm;*.docx;*.txt;*.csv;*.tsv"),
                    Filter("Excel Files", "*.xlsx;*.xlsm"),
                    Filter("Word Files", "*.docx"),
                    Filter("Text Files", "*.txt;*.csv;*.tsv"),
                    Filter("All Files", "*.*"),
                ]
                default_ext = "xlsx"

            path = pick_open_file(
                title="대상자 파일 선택",
                filters=filters,
                default_ext=default_ext,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return

        if not path:
            return

        self._import_file_from_path(path, source_label="파일")

    def _import_file_from_path(self, path: str, source_label: str) -> None:
        if not is_supported_contact_import_file(path):
            QMessageBox.warning(
                self,
                "지원 형식 아님",
                "지원 확장자: .xlsx, .xlsm, .docx, .txt, .csv, .tsv"
            )
            return

        self._set_busy(True)
        self._on_status(f"{source_label} 읽는 중...")

        def parse_job():
            return import_contacts_file(path)

        run_bg(
            parse_job,
            on_done=lambda result: self._after_parse(result, source_label=source_label),
            on_error=self._show_bg_error,
        )

    def _open_paste_dialog(self) -> None:
        dlg = PasteImportDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        text = dlg.get_text()
        self._import_pasted_text(text, source_label="붙여넣기")

    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text() or ""
        if not text.strip():
            QMessageBox.information(self, "안내", "클립보드에 업로드할 텍스트가 없습니다.")
            return
        self._import_pasted_text(text, source_label="클립보드")

    def _import_pasted_text(self, text: str, source_label: str) -> None:
        self._set_busy(True)
        self._on_status(f"{source_label} 읽는 중...")

        def parse_job():
            return import_contacts_text(text)

        run_bg(
            parse_job,
            on_done=lambda result: self._after_parse(result, source_label=source_label),
            on_error=self._show_bg_error,
        )

    def _after_parse(self, result, source_label: str) -> None:
        if result.errors:
            self._set_busy(False)
            QMessageBox.warning(self, f"{source_label} 오류", "\n".join(result.errors))
            return

        if not result.rows:
            self._set_busy(False)
            QMessageBox.information(self, "안내", "등록할 데이터가 없습니다.")
            return

        preview = ImportPreviewDialog(result.rows, parent=self)
        r = preview.exec()

        if r != QDialog.Accepted:
            self._set_busy(False)
            self._on_status(f"{source_label} 등록 취소")
            return

        self._on_status("DB 저장 중...")

        def db_job():
            inserted, dup_skipped = self.service.repo.insert_many(result.rows)
            rows = self.service.repo.search_contacts("")
            return inserted, dup_skipped, rows

        def db_done(res):
            inserted, dup_skipped, rows = res
            self.store.load_rows(rows)
            self.reload()

            self._suppress_contacts_event = True
            try:
                app_events.contacts_changed.emit()
            finally:
                self._suppress_contacts_event = False

            self._set_busy(False)

            msg = f"{source_label} 등록 완료: {inserted}건"
            if dup_skipped:
                msg += f" / 중복 스킵 {dup_skipped}건(사번/전화번호)"
            self._on_status(msg)
            QMessageBox.information(self, "완료", msg)

        run_bg(db_job, on_done=db_done, on_error=self._show_bg_error)

    def _download_template(self) -> None:
        try:
            path = pick_save_file(
                title="샘플 서식 저장",
                filters=[Filter("Excel Files", "*.xlsx"), Filter("All Files", "*.*")],
                default_filename="contacts_template.xlsx",
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 위치 선택기 실행 실패:\n{e}")
            return

        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            create_template_xlsx(path)
            self._on_status(f"샘플 서식 저장 완료: {path}")
            QMessageBox.information(self, "완료", "샘플 서식을 저장했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"샘플 서식 생성 실패:\n{e}")

    def _export_excel(self) -> None:
        try:
            path = pick_save_file(
                title="대상자 엑셀 내보내기",
                filters=[Filter("Excel Files", "*.xlsx"), Filter("All Files", "*.*")],
                default_filename="contacts_export.xlsx",
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 위치 선택기 실행 실패:\n{e}")
            return

        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        self._set_busy(True)
        self._on_status("엑셀 내보내기 준비 중...")

        def job():
            export_rows = []
            for pr in range(self.proxy.rowCount()):
                idx = self.proxy.index(pr, 2)
                src_idx = self.proxy.mapToSource(idx)
                c = self.model.contact_at(src_idx.row())
                export_rows.append((c.emp_id, c.name, c.phone, c.agency, c.branch))

            export_contacts_xlsx(path, export_rows)
            return len(export_rows)

        def done(cnt: int):
            self._set_busy(False)
            self._on_status(f"엑셀 내보내기 완료: {cnt}건")
            QMessageBox.information(self, "완료", f"엑셀 내보내기 완료: {cnt}건")

        run_bg(job, on_done=done, on_error=self._show_bg_error)

    def _toggle_all_checked(self, checked: bool) -> None:
        if checked:
            ids = []
            for pr in range(self.proxy.rowCount()):
                idx = self.proxy.index(pr, 2)
                src = self.proxy.mapToSource(idx)
                c = self.model.contact_at(src.row())
                ids.append(c.id)
            self.model.set_checked_ids(ids)
        else:
            self.model.clear_checked()
        self._sync_header_checkbox()

    def _sync_header_checkbox(self) -> None:
        header = self.table.horizontalHeader()
        if not isinstance(header, CheckableHeader):
            return

        total_visible = self.proxy.rowCount()
        if total_visible == 0:
            header.set_check_state(Qt.Unchecked)
            return

        checked_visible = 0
        checked_set = set(self.model.checked_ids())

        for pr in range(total_visible):
            idx = self.proxy.index(pr, 2)
            src = self.proxy.mapToSource(idx)
            c = self.model.contact_at(src.row())
            if c.id in checked_set:
                checked_visible += 1

        if checked_visible == 0:
            header.set_check_state(Qt.Unchecked)
        elif checked_visible == total_visible:
            header.set_check_state(Qt.Checked)
        else:
            header.set_check_state(Qt.PartiallyChecked)

    def _on_table_clicked(self, index) -> None:
        if index.column() != 0:
            return

        src = self.proxy.mapToSource(index)
        if not src.isValid():
            return

        current = self.model.data(src, Qt.CheckStateRole)
        new_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
        self.model.setData(src, new_state, Qt.CheckStateRole)
        self._sync_header_checkbox()

    def _on_contact_double_clicked(self, index) -> None:
        if not index.isValid():
            return

        row = index.row()
        src = self.proxy.mapToSource(self.proxy.index(row, 0))
        if not src.isValid():
            return

        c = self.model.contact_at(src.row())
        ok = edit_contact_by_id(
            self,
            contacts_service=self.service,
            contact_id=int(c.id),
        )
        if not ok:
            return

        emp_disp = (c.emp_id or "").strip() or "(사번없음)"
        self._on_status(f"수정 완료: {c.name} ({emp_disp})")
