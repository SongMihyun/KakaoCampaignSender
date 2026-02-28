from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QModelIndex, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QMessageBox, QAbstractItemView, QDialog, QComboBox, QHeaderView
)

from app.data.groups_repo import GroupsRepo, GroupRow
from app.data.contacts_repo import ContactsRepo
from app.stores.contacts_store import ContactsStore, ContactMem

from ui.pages.group_dialog import GroupDialog
from ui.pages.contacts_dialog import ContactDialog

from ui.widgets.checkable_header import CheckableHeader
from ui.utils.worker import run_bg
from ui.app_events import app_events


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
        repo: GroupsRepo,
        contacts_repo: ContactsRepo,
        contacts_store: ContactsStore,
        on_status: Optional[Callable[[str], None]] = None
    ) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.repo = repo
        self.contacts_repo = contacts_repo
        self.contacts_store = contacts_store
        self._on_status = on_status or (lambda _: None)

        self._current_group: GroupRow | None = None
        self._groups_cache: list[GroupRow] = []

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

        # LEFT: candidates
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
        self.candidates_model.setHorizontalHeaderLabels(["No", "사번", "이름", "전화번호", "대리점명", "지사명", "ID"])
        self.tbl_candidates.setModel(self.candidates_model)

        hdr_cand = CheckableHeader(Qt.Horizontal, self.tbl_candidates, check_col=self.COL_NO)
        self.tbl_candidates.setHorizontalHeader(hdr_cand)
        hdr_cand.toggled.connect(lambda checked: self._toggle_select_all(self.tbl_candidates, checked))
        self.tbl_candidates.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_header_by_selection(self.tbl_candidates)
        )

        # ✅ 후보 더블클릭 = 대상자 수정
        self.tbl_candidates.doubleClicked.connect(self._on_candidates_double_clicked)

        self._apply_table_layout(self.tbl_candidates)
        self._hide_id_column(self.tbl_candidates)

        self.btn_add_to_group = QPushButton("그룹에 추가 ▶")
        left.addWidget(self.tbl_candidates, 1)
        left.addWidget(self.btn_add_to_group)

        # RIGHT: members
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
        self.members_model.setHorizontalHeaderLabels(["No", "사번", "이름", "전화번호", "대리점명", "지사명", "ID"])
        self.tbl_members.setModel(self.members_model)

        hdr_mem = CheckableHeader(Qt.Horizontal, self.tbl_members, check_col=self.COL_NO)
        self.tbl_members.setHorizontalHeader(hdr_mem)
        hdr_mem.toggled.connect(lambda checked: self._toggle_select_all(self.tbl_members, checked))
        self.tbl_members.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_header_by_selection(self.tbl_members)
        )

        # ✅ 멤버 더블클릭 = 대상자 수정
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

        # Debounce timers
        self._cand_timer = QTimer(self)
        self._cand_timer.setSingleShot(True)
        self._cand_timer.timeout.connect(lambda: self._load_candidates(self._candidate_keyword))

        self._mem_timer = QTimer(self)
        self._mem_timer.setSingleShot(True)
        self._mem_timer.timeout.connect(lambda: self._load_members(
            self._current_group.id if self._current_group else None,
            self._member_keyword
        ))

        # events
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

        # ✅ 대상자 변경 이벤트 수신 -> 자동 갱신
        app_events.contacts_changed.connect(self._on_contacts_changed)  # type: ignore[arg-type]

        # init
        self.reload_groups(select_group_id=None)
        self._load_candidates("")

    # -----------------
    # Normalize helpers
    # -----------------
    @staticmethod
    def _norm_optional(v: str | None) -> str:
        return (v or "").strip()

    @staticmethod
    def _norm_required(v: str | None) -> str:
        return (v or "").strip()

    # -----------------
    # UI state helpers
    # -----------------
    def _update_group_buttons(self) -> None:
        has_group = self._current_group is not None
        self.btn_group_edit.setEnabled(has_group)
        self.btn_group_del.setEnabled(has_group)
        self.btn_add_to_group.setEnabled(has_group)
        self.btn_remove_from_group.setEnabled(has_group)

    # -----------------
    # Contacts changed event handler
    # -----------------
    def _on_contacts_changed(self) -> None:
        current_id = self._current_group.id if self._current_group else None
        self.reload_groups(select_group_id=current_id)
        self._load_members(current_id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    # -----------------
    # Table setup
    # -----------------
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

    # -----------------
    # Group combo
    # -----------------
    def reload_groups(self, select_group_id: int | None = None) -> None:
        self.cbo_groups.blockSignals(True)
        self.cbo_groups.clear()

        self.cbo_groups.addItem("(선택 안 함)", None)
        self._groups_cache = self.repo.list_groups()

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

        found: GroupRow | None = None
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

    # -----------------
    # Group CRUD
    # -----------------
    def _create_group(self) -> None:
        dlg = GroupDialog("그룹 생성", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_data()
        name = (data.get("name") or "").strip()
        memo = (data.get("memo") or "").strip()

        if not name:
            QMessageBox.warning(self, "오류", "그룹명을 입력하세요.")
            return

        try:
            new_id = self.repo.create_group(name, memo)
        except ValueError as e:
            QMessageBox.warning(self, "중복 오류", str(e))
            return

        self._current_group = GroupRow(new_id, name, memo)
        self.reload_groups(select_group_id=new_id)

    def _edit_group(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "수정할 그룹을 선택하세요.")
            return

        dlg = GroupDialog("그룹 수정", preset={"name": g.name, "memo": g.memo}, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_data()
        name = (data.get("name") or "").strip()
        memo = (data.get("memo") or "").strip()

        if not name:
            QMessageBox.warning(self, "오류", "그룹명은 필수입니다.")
            return

        try:
            self.repo.update_group(g.id, name, memo)
        except ValueError as e:
            QMessageBox.warning(self, "오류", str(e))
            return

        self._current_group = GroupRow(g.id, name, memo)
        self.reload_groups(select_group_id=g.id)

    def _delete_group(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "삭제할 그룹을 선택하세요.")
            return

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"그룹 '{g.name}'을(를) 삭제하시겠습니까?\n(멤버 매핑도 함께 삭제됩니다)",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        self.repo.delete_group(g.id)
        self._current_group = None
        self.reload_groups(select_group_id=None)

    # -----------------
    # Search / Load
    # -----------------
    def _on_candidate_search_changed(self, text: str) -> None:
        self._candidate_keyword = (text or "").strip()
        self._cand_timer.start(250)

    def _on_member_search_changed(self, text: str) -> None:
        self._member_keyword = (text or "").strip()
        self._mem_timer.start(250)

    def _load_candidates(self, keyword: str) -> None:
        kw = (keyword or "").strip()

        def job():
            return self.contacts_store.search(kw)

        def done(rows: list[ContactMem]):
            self.candidates_model.setRowCount(0)

            shown = 0
            for m in rows:
                shown += 1
                in_group = int(m.id) in self._member_id_set
                self.candidates_model.appendRow(self._mem_to_items(shown, m, disabled=in_group))

            self.tbl_candidates.clearSelection()
            self._sync_header_by_selection(self.tbl_candidates)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _load_members(self, group_id: int | None, keyword: str) -> None:
        gid = group_id
        kw = (keyword or "").strip().lower()

        def job():
            if not gid:
                return ([], set())
            member_ids = self.repo.list_group_member_ids(int(gid))
            id_set = {int(x) for x in (member_ids or [])}
            members = self.contacts_store.get_many(member_ids)
            return (members, id_set)

        def done(res):
            members, id_set = res
            self.members_model.setRowCount(0)
            self._member_id_set = set(id_set)

            if not gid:
                self.tbl_members.clearSelection()
                self._sync_header_by_selection(self.tbl_members)
                self._load_candidates(self._candidate_keyword)
                return

            def match(m: ContactMem) -> bool:
                if not kw:
                    return True
                hay = " ".join([m.emp_id, m.name, m.phone, m.agency, m.branch]).lower()
                return kw in hay

            shown = 0
            for m in members:
                if match(m):
                    shown += 1
                    self.members_model.appendRow(self._mem_to_items(shown, m, disabled=False))

            self.tbl_members.clearSelection()
            self._sync_header_by_selection(self.tbl_members)
            self._load_candidates(self._candidate_keyword)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    # -----------------
    # Double click -> edit
    # -----------------
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

        emp = (model.item(row, self.COL_EMP).text() if model.item(row, self.COL_EMP) else "")
        name = (model.item(row, self.COL_NAME).text() if model.item(row, self.COL_NAME) else "")
        phone = (model.item(row, self.COL_PHONE).text() if model.item(row, self.COL_PHONE) else "")
        agency = (model.item(row, self.COL_AGENCY).text() if model.item(row, self.COL_AGENCY) else "")
        branch = (model.item(row, self.COL_BRANCH).text() if model.item(row, self.COL_BRANCH) else "")

        preset_obj = type("Tmp", (), {
            "emp_id": emp or "",
            "name": name or "",
            "phone": phone or "",
            "agency": agency or "",
            "branch": branch or "",
        })()

        dlg = ContactDialog("대상자 수정", preset=preset_obj, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        data = dlg.get_contact()

        new_name = self._norm_required(data.get("name"))
        new_emp_id = self._norm_optional(data.get("emp_id"))
        new_phone = self._norm_optional(data.get("phone"))
        new_agency = self._norm_optional(data.get("agency"))
        new_branch = self._norm_optional(data.get("branch"))

        if not new_name:
            QMessageBox.warning(self, "입력 오류", "이름은 필수입니다.")
            return

        try:
            self.contacts_repo.update(
                row_id=contact_id,
                emp_id=new_emp_id,
                name=new_name,
                phone=new_phone,
                agency=new_agency,
                branch=new_branch,
            )
            self.contacts_store.update(
                contact_id=contact_id,
                emp_id=new_emp_id,
                name=new_name,
                phone=new_phone,
                agency=new_agency,
                branch=new_branch,
            )
        except ValueError as e:
            QMessageBox.warning(self, "중복 오류", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "오류", f"대상자 저장 실패:\n{e}")
            return

        app_events.contacts_changed.emit()
        self._on_status(f"대상자 수정 저장: {new_name} ({new_emp_id if new_emp_id else '사번없음'})")

        current_id = self._current_group.id if self._current_group else None
        self._load_members(current_id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    # -----------------
    # Add/Remove actions
    # -----------------
    def _add_selected_candidates(self) -> None:
        g = self._current_group
        if not g:
            QMessageBox.information(self, "안내", "먼저 그룹을 선택하세요.")
            return

        ids = self._selected_contact_ids(self.tbl_candidates, self.candidates_model)
        if not ids:
            QMessageBox.information(self, "안내", "추가할 대상을 선택하세요.")
            return

        inserted, skipped = self.repo.add_members(g.id, ids)
        self._load_members(g.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

        msg = f"그룹 추가 완료: {inserted}건"
        if skipped:
            msg += f" / 중복 스킵 {skipped}건"
        QMessageBox.information(self, "완료", msg)

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
            self, "제거 확인",
            f"{len(ids)}명을 그룹에서 제거하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        self.repo.remove_members(g.id, ids)
        self._load_members(g.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)
        QMessageBox.information(self, "완료", f"그룹에서 제거했습니다: {len(ids)}건")

    # -----------------
    # Header 체크박스
    # -----------------
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

    # -----------------
    # Helpers
    # -----------------
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