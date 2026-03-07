# FILE: src/frontend/pages/groups/page.py
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QModelIndex, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QMessageBox,
    QAbstractItemView,
    QDialog,
    QComboBox,
    QHeaderView,
)

from backend.domains.contacts.service import ContactsService
from backend.domains.groups.dto import GroupCreateDTO, GroupUpdateDTO
from backend.domains.groups.service import GroupsService
from backend.stores.contacts_store import ContactsStore, ContactMem

from frontend.pages.groups.dialog import GroupDialog
from frontend.widgets.checkable_header import CheckableHeader
from frontend.utils.contact_edit import edit_contact_by_id
from frontend.utils.worker import run_bg
from frontend.app.app_events import app_events


class GroupsPage(QWidget):
    COL_NO = 0
    COL_EMP = 1
    COL_NAME = 2
    COL_PHONE = 3
    COL_AGENCY = 4
    COL_BRANCH = 5
    COL_ID_HIDDEN = 6

    def __init__(
        self,
        service: GroupsService,
        contacts_service: ContactsService,
        contacts_store: ContactsStore,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.setObjectName("Page")

        self.service = service
        self.contacts_service = contacts_service
        self.contacts_store = contacts_store
        self._on_status = on_status or (lambda _: None)

        self._current_group = None
        self._groups_cache = []

        self._candidate_keyword = ""
        self._member_keyword = ""
        self._member_id_set: set[int] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("그룹 관리")
        title.setObjectName("PageTitle")
        desc = QLabel("발송 대상자를 그룹으로 구성/관리합니다. (검색 → 선택 → 그룹 추가/제거)")
        desc.setObjectName("PageDesc")

        top = QHBoxLayout()
        top.setSpacing(8)

        top.addWidget(QLabel("그룹 선택"))
        self.cbo_groups = QComboBox()
        self.cbo_groups.setMinimumWidth(280)

        self.btn_group_add = QPushButton("그룹 생성")
        self.btn_group_edit = QPushButton("그룹 수정")
        self.btn_group_del = QPushButton("그룹 삭제")

        top.addWidget(self.cbo_groups)
        top.addWidget(self.btn_group_add)
        top.addWidget(self.btn_group_edit)
        top.addWidget(self.btn_group_del)
        top.addStretch(1)

        main = QHBoxLayout()
        main.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(QLabel("대상자 검색 결과"))

        cand_search_row = QHBoxLayout()
        self.cand_search = QLineEdit()
        self.cand_search.setPlaceholderText("후보 검색: 이름/사번/전화/대리점/지사")
        self.btn_cand_clear = QPushButton("초기화")
        cand_search_row.addWidget(self.cand_search, 1)
        cand_search_row.addWidget(self.btn_cand_clear)
        left.addLayout(cand_search_row)

        self.tbl_candidates = QTableView()
        self._setup_table(self.tbl_candidates)

        self.candidates_model = QStandardItemModel(0, 7, self)
        self.candidates_model.setHorizontalHeaderLabels(
            ["No", "사번", "이름", "전화번호", "대리점명", "지사명", "ID"]
        )
        self.tbl_candidates.setModel(self.candidates_model)

        hdr_cand = CheckableHeader(Qt.Horizontal, self.tbl_candidates, check_col=self.COL_NO)
        self.tbl_candidates.setHorizontalHeader(hdr_cand)
        hdr_cand.toggled.connect(lambda checked: self._toggle_select_all(self.tbl_candidates, checked))
        self.tbl_candidates.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_header_by_selection(self.tbl_candidates)
        )
        self.tbl_candidates.doubleClicked.connect(self._on_candidates_double_clicked)

        self._apply_table_layout(self.tbl_candidates)
        self._hide_id_column(self.tbl_candidates)

        self.btn_add_to_group = QPushButton("그룹에 추가 ▶")
        left.addWidget(self.tbl_candidates, 1)
        left.addWidget(self.btn_add_to_group)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(QLabel("그룹 멤버"))

        mem_search_row = QHBoxLayout()
        self.mem_search = QLineEdit()
        self.mem_search.setPlaceholderText("멤버 검색: 이름/사번/전화/대리점/지사")
        self.btn_mem_clear = QPushButton("초기화")
        mem_search_row.addWidget(self.mem_search, 1)
        mem_search_row.addWidget(self.btn_mem_clear)
        right.addLayout(mem_search_row)

        self.tbl_members = QTableView()
        self._setup_table(self.tbl_members)

        self.members_model = QStandardItemModel(0, 7, self)
        self.members_model.setHorizontalHeaderLabels(
            ["No", "사번", "이름", "전화번호", "대리점명", "지사명", "ID"]
        )
        self.tbl_members.setModel(self.members_model)

        hdr_mem = CheckableHeader(Qt.Horizontal, self.tbl_members, check_col=self.COL_NO)
        self.tbl_members.setHorizontalHeader(hdr_mem)
        hdr_mem.toggled.connect(lambda checked: self._toggle_select_all(self.tbl_members, checked))
        self.tbl_members.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_header_by_selection(self.tbl_members)
        )
        self.tbl_members.doubleClicked.connect(self._on_members_double_clicked)

        self._apply_table_layout(self.tbl_members)
        self._hide_id_column(self.tbl_members)

        self.btn_remove_from_group = QPushButton("◀ 그룹에서 제거")
        right.addWidget(self.tbl_members, 1)
        right.addWidget(self.btn_remove_from_group)

        main.addLayout(left, 5)
        main.addLayout(right, 5)

        root.addWidget(title)
        root.addWidget(desc)
        root.addLayout(top)
        root.addLayout(main, 1)

        self._cand_timer = QTimer(self)
        self._cand_timer.setSingleShot(True)
        self._cand_timer.timeout.connect(lambda: self._load_candidates(self._candidate_keyword))

        self._mem_timer = QTimer(self)
        self._mem_timer.setSingleShot(True)
        self._mem_timer.timeout.connect(
            lambda: self._load_members(
                self._current_group.id if self._current_group else None,
                self._member_keyword,
            )
        )

        self.cbo_groups.currentIndexChanged.connect(self._on_group_combo_changed)

        self.btn_group_add.clicked.connect(self._create_group)
        self.btn_group_edit.clicked.connect(self._edit_group)
        self.btn_group_del.clicked.connect(self._delete_group)

        self.btn_add_to_group.clicked.connect(self._add_selected_candidates)
        self.btn_remove_from_group.clicked.connect(self._remove_selected_members)

        self.cand_search.textChanged.connect(self._on_candidate_search_changed)
        self.btn_cand_clear.clicked.connect(lambda: self.cand_search.setText(""))

        self.mem_search.textChanged.connect(self._on_member_search_changed)
        self.btn_mem_clear.clicked.connect(lambda: self.mem_search.setText(""))

        app_events.contacts_changed.connect(self._on_contacts_changed)  # type: ignore[arg-type]

        self.reload_groups(select_group_id=None)
        self._load_candidates("")

    def refresh(self) -> None:
        current_id = self._current_group.id if self._current_group else None
        self.reload_groups(select_group_id=current_id)

    def _update_group_buttons(self) -> None:
        has_group = self._current_group is not None
        self.btn_group_edit.setEnabled(has_group)
        self.btn_group_del.setEnabled(has_group)
        self.btn_add_to_group.setEnabled(has_group)
        self.btn_remove_from_group.setEnabled(has_group)

    def _on_contacts_changed(self) -> None:
        current_id = self._current_group.id if self._current_group else None
        self.reload_groups(select_group_id=current_id)
        self._load_members(current_id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    def _setup_table(self, table: QTableView) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("QTableView { gridline-color: #e5e7eb; }")

    def _apply_table_layout(self, table: QTableView) -> None:
        h = table.horizontalHeader()

        table.setColumnWidth(self.COL_NO, 30)
        table.setColumnWidth(self.COL_EMP, 80)
        table.setColumnWidth(self.COL_NAME, 60)
        table.setColumnWidth(self.COL_PHONE, 100)
        table.setColumnWidth(self.COL_AGENCY, 70)
        h.setStretchLastSection(True)

        h.setSectionResizeMode(self.COL_NO, QHeaderView.Fixed)
        h.setSectionResizeMode(self.COL_EMP, QHeaderView.Fixed)
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.Fixed)
        h.setSectionResizeMode(self.COL_PHONE, QHeaderView.Fixed)
        h.setSectionResizeMode(self.COL_AGENCY, QHeaderView.Fixed)
        h.setSectionResizeMode(self.COL_BRANCH, QHeaderView.Stretch)

    def _hide_id_column(self, table: QTableView) -> None:
        table.setColumnHidden(self.COL_ID_HIDDEN, True)
        table.setColumnWidth(self.COL_ID_HIDDEN, 0)
        h = table.horizontalHeader()
        h.setSectionResizeMode(self.COL_ID_HIDDEN, QHeaderView.Fixed)

    def reload_groups(self, select_group_id: int | None = None) -> None:
        self.cbo_groups.blockSignals(True)
        self.cbo_groups.clear()

        self.cbo_groups.addItem("(선택 안 함)", None)
        self._groups_cache = self.service.list_groups()

        if not self._groups_cache:
            self._current_group = None
            self.cbo_groups.setCurrentIndex(0)
            self.cbo_groups.blockSignals(False)

            self._update_group_buttons()
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        for g in self._groups_cache:
            self.cbo_groups.addItem(g.name, g.id)

        target_id = select_group_id
        if target_id is None and self._current_group:
            target_id = self._current_group.id

        if target_id is None:
            self._current_group = None
            self.cbo_groups.setCurrentIndex(0)
            self.cbo_groups.blockSignals(False)

            self._update_group_buttons()
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        found = None
        index_to_select = 0
        for i, g in enumerate(self._groups_cache):
            if g.id == target_id:
                found = g
                index_to_select = i + 1
                break

        if not found:
            self._current_group = None
            self.cbo_groups.setCurrentIndex(0)
            self.cbo_groups.blockSignals(False)

            self._update_group_buttons()
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        self._current_group = found
        self.cbo_groups.setCurrentIndex(index_to_select)
        self.cbo_groups.blockSignals(False)

        self._update_group_buttons()
        self._load_members(self._current_group.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    def _on_group_combo_changed(self, idx: int) -> None:
        group_id = self.cbo_groups.currentData()

        if group_id is None:
            self._current_group = None
            self._update_group_buttons()
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        gid = int(group_id)
        g = next((x for x in self._groups_cache if x.id == gid), None)
        if not g:
            self._current_group = None
            self.cbo_groups.setCurrentIndex(0)
            self._update_group_buttons()
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        self._current_group = g
        self._update_group_buttons()
        self._load_members(g.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    def _create_group(self) -> None:
        dlg = GroupDialog("그룹 생성", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_data()
        dto = GroupCreateDTO(
            name=(data.get("name") or "").strip(),
            memo=(data.get("memo") or "").strip(),
        )

        if not dto.name:
            QMessageBox.warning(self, "오류", "그룹명을 입력하세요.")
            return

        try:
            new_id = self.service.create_group(dto)
        except ValueError as e:
            QMessageBox.warning(self, "중복 오류", str(e))
            return

        self.reload_groups(select_group_id=new_id)
        self._on_status(f"그룹 생성 완료: {dto.name}")

    def _edit_group(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "수정할 그룹을 선택하세요.")
            return

        dlg = GroupDialog("그룹 수정", preset={"name": g.name, "memo": g.memo}, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_data()
        dto = GroupUpdateDTO(
            group_id=g.id,
            name=(data.get("name") or "").strip(),
            memo=(data.get("memo") or "").strip(),
        )

        if not dto.name:
            QMessageBox.warning(self, "오류", "그룹명은 필수입니다.")
            return

        try:
            self.service.update_group(dto)
        except ValueError as e:
            QMessageBox.warning(self, "오류", str(e))
            return

        self.reload_groups(select_group_id=g.id)
        self._on_status(f"그룹 수정 완료: {dto.name}")

    def _delete_group(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "삭제할 그룹을 선택하세요.")
            return

        ok = QMessageBox.question(
            self,
            "삭제 확인",
            f"그룹 '{g.name}'을(를) 삭제하시겠습니까?\n(멤버 매핑도 함께 삭제됩니다)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        self.service.delete_group(g.id)
        self._current_group = None
        self.reload_groups(select_group_id=None)
        self._on_status(f"그룹 삭제 완료: {g.name}")

    def _on_candidate_search_changed(self, text: str) -> None:
        self._candidate_keyword = (text or "").strip()
        self._cand_timer.start(250)

    def _on_member_search_changed(self, text: str) -> None:
        self._member_keyword = (text or "").strip()
        self._mem_timer.start(250)

    def _load_candidates(self, keyword: str) -> None:
        kw = (keyword or "").strip()

        def job():
            return self.service.search_candidate_contacts(
                kw,
                exclude_contact_ids=self._member_id_set,
            )

        def done(rows: list[ContactMem]):
            self.candidates_model.setRowCount(0)

            shown = 0
            for m in rows:
                shown += 1
                self.candidates_model.appendRow(self._mem_to_items(shown, m, disabled=False))

            self.tbl_candidates.clearSelection()
            self._sync_header_by_selection(self.tbl_candidates)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _load_members(self, group_id: int | None, keyword: str) -> None:
        gid = group_id
        kw = (keyword or "").strip()

        def job():
            if not gid:
                return ([], set())
            members = self.service.get_member_contacts(int(gid), kw)
            member_ids = {int(m.id) for m in members}
            all_member_ids = set(self.service.list_member_ids(int(gid)))
            return (members, all_member_ids if kw else member_ids)

        def done(res):
            members, id_set = res
            self.members_model.setRowCount(0)
            self._member_id_set = set(id_set)

            if not gid:
                self.tbl_members.clearSelection()
                self._sync_header_by_selection(self.tbl_members)
                self._load_candidates(self._candidate_keyword)
                return

            shown = 0
            for m in members:
                shown += 1
                self.members_model.appendRow(self._mem_to_items(shown, m, disabled=False))

            self.tbl_members.clearSelection()
            self._sync_header_by_selection(self.tbl_members)
            self._load_candidates(self._candidate_keyword)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _on_candidates_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._open_contact_edit_from_model(self.candidates_model, index.row())

    def _on_members_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._open_contact_edit_from_model(self.members_model, index.row())

    def _open_contact_edit_from_model(self, model: QStandardItemModel, row: int) -> None:
        no_item = model.item(row, self.COL_NO)
        if no_item is None or not (no_item.flags() & Qt.ItemIsEnabled):
            return

        id_item = model.item(row, self.COL_ID_HIDDEN)
        if id_item is None:
            return

        try:
            contact_id = int(id_item.text())
        except ValueError:
            return

        fallback_preset = {
            "emp_id": model.item(row, self.COL_EMP).text() if model.item(row, self.COL_EMP) else "",
            "name": model.item(row, self.COL_NAME).text() if model.item(row, self.COL_NAME) else "",
            "phone": model.item(row, self.COL_PHONE).text() if model.item(row, self.COL_PHONE) else "",
            "agency": model.item(row, self.COL_AGENCY).text() if model.item(row, self.COL_AGENCY) else "",
            "branch": model.item(row, self.COL_BRANCH).text() if model.item(row, self.COL_BRANCH) else "",
        }

        ok = edit_contact_by_id(
            self,
            contacts_service=self.contacts_service,
            contact_id=contact_id,
            fallback_preset=fallback_preset,
        )
        if not ok:
            return

        name = (fallback_preset.get("name") or "").strip()
        emp_id = (fallback_preset.get("emp_id") or "").strip()
        self._on_status(f"대상자 수정 저장: {name} ({emp_id if emp_id else '사번없음'})")

    def _add_selected_candidates(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "먼저 그룹을 선택하세요.")
            return

        ids = self._selected_contact_ids(self.tbl_candidates, self.candidates_model)
        if not ids:
            QMessageBox.information(self, "안내", "추가할 대상을 선택하세요.")
            return

        inserted, skipped = self.service.add_members(g.id, ids)
        self._load_members(g.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

        msg = f"그룹 추가 완료: {inserted}건"
        if skipped:
            msg += f" / 중복 스킵 {skipped}건"
        QMessageBox.information(self, "완료", msg)
        self._on_status(msg)

    def _remove_selected_members(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "먼저 그룹을 선택하세요.")
            return

        ids = self._selected_contact_ids(self.tbl_members, self.members_model)
        if not ids:
            QMessageBox.information(self, "안내", "제거할 멤버를 선택하세요.")
            return

        ok = QMessageBox.question(
            self,
            "제거 확인",
            f"{len(ids)}명을 그룹에서 제거하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        removed = self.service.remove_members(g.id, ids)
        self._load_members(g.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

        msg = f"그룹에서 제거했습니다: {removed}건"
        QMessageBox.information(self, "완료", msg)
        self._on_status(msg)

    def _toggle_select_all(self, table: QTableView, checked: bool) -> None:
        model = table.model()
        sel = table.selectionModel()
        if model is None or sel is None or model.rowCount() == 0:
            return

        if not checked:
            table.clearSelection()
            self._sync_header_by_selection(table)
            return

        selection = QItemSelection()
        for r in range(model.rowCount()):
            idx_no = model.index(r, self.COL_NO)
            if not (model.flags(idx_no) & Qt.ItemIsEnabled):
                continue
            left = model.index(r, 0)
            right = model.index(r, model.columnCount() - 1)
            selection.merge(QItemSelection(left, right), QItemSelectionModel.Select)

        sel.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self._sync_header_by_selection(table)

    def _sync_header_by_selection(self, table: QTableView) -> None:
        header = table.horizontalHeader()
        if not isinstance(header, CheckableHeader):
            return

        model = table.model()
        sel = table.selectionModel()
        if model is None or sel is None:
            header.set_check_state(Qt.Unchecked)
            return

        total = 0
        selected = 0

        for r in range(model.rowCount()):
            idx_no = model.index(r, self.COL_NO)
            if not (model.flags(idx_no) & Qt.ItemIsEnabled):
                continue

            total += 1
            if sel.isRowSelected(r, QModelIndex()):
                selected += 1

        if total == 0 or selected == 0:
            header.set_check_state(Qt.Unchecked)
        elif selected == total:
            header.set_check_state(Qt.Checked)
        else:
            header.set_check_state(Qt.PartiallyChecked)

    def _mem_to_items(self, no: int, m: ContactMem, disabled: bool = False):
        no_item = QStandardItem(str(no))
        emp = QStandardItem(m.emp_id or "")
        name = QStandardItem(m.name or "")
        phone = QStandardItem(m.phone or "")
        agency = QStandardItem(m.agency or "")
        branch = QStandardItem(m.branch or "")
        hidden_id = QStandardItem(str(m.id))

        items = [no_item, emp, name, phone, agency, branch, hidden_id]

        for it in items:
            it.setEditable(False)
            if disabled:
                it.setFlags(it.flags() & ~(Qt.ItemIsEnabled | Qt.ItemIsSelectable))

        return items

    def _selected_contact_ids(self, table: QTableView, model: QStandardItemModel) -> list[int]:
        ids: list[int] = []
        sel = table.selectionModel()
        if not sel:
            return ids

        for idx in sel.selectedRows():
            row = idx.row()
            id_item = model.item(row, self.COL_ID_HIDDEN)
            if id_item is None:
                continue
            try:
                ids.append(int(id_item.text()))
            except ValueError:
                pass

        return sorted(set(ids))