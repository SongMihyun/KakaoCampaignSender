# src/ui/pages/groups_page.py
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QModelIndex, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QMessageBox, QAbstractItemView, QDialog, QComboBox, QHeaderView
)

from app.data.groups_repo import GroupsRepo, GroupRow, ContactRow
from ui.pages.group_dialog import GroupDialog
from ui.widgets.checkable_header import CheckableHeader

from ui.utils.worker import run_bg

# ✅ 앱 전역 이벤트(대상자 변경 시 그룹관리 자동 갱신)
from ui.app_events import app_events


class GroupsPage(QWidget):
    # 컬럼 인덱스
    COL_NO = 0
    COL_EMP = 1
    COL_NAME = 2
    COL_PHONE = 3
    COL_AGENCY = 4
    COL_BRANCH = 5
    COL_ID_HIDDEN = 6

    def __init__(self, repo: GroupsRepo, on_status: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.repo = repo
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

        # TOP: 그룹 선택 + CRUD
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

        # MAIN: 후보 | 멤버
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

        # 7컬럼: [No][사번][이름][전화][대리점][지사][숨김ID]
        self.candidates_model = QStandardItemModel(0, 7, self)
        self.candidates_model.setHorizontalHeaderLabels(["No", "사번", "이름", "전화번호", "대리점명", "지사명", "ID"])
        self.tbl_candidates.setModel(self.candidates_model)

        # ✅ No 헤더에 체크박스
        hdr_cand = CheckableHeader(Qt.Horizontal, self.tbl_candidates, check_col=self.COL_NO)
        self.tbl_candidates.setHorizontalHeader(hdr_cand)
        hdr_cand.toggled.connect(lambda checked: self._toggle_select_all(self.tbl_candidates, checked))
        self.tbl_candidates.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_header_by_selection(self.tbl_candidates)
        )

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

        # -----------------
        # Debounce timers (핵심)
        # -----------------
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

        # ✅ 대상자 변경 이벤트 수신 -> 그룹관리 화면 자동 갱신
        app_events.contacts_changed.connect(self._on_contacts_changed)  # type: ignore[arg-type]

        # init
        self.reload_groups()
        self._load_candidates("")

    # -----------------
    # ✅ Contacts changed event handler
    # -----------------
    def _on_contacts_changed(self) -> None:
        """
        ContactsPage에서 대상자(contacts)가 추가/수정/삭제/엑셀등록 등으로 변경되면
        그룹관리 화면(후보/멤버/disable 상태)을 즉시 최신화한다.
        """
        current_id = self._current_group.id if self._current_group else None

        # 그룹 콤보/캐시 갱신(현재 선택 유지 시도)
        self.reload_groups(select_group_id=current_id)

        # 멤버/후보 재조회
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

        self._groups_cache = self.repo.list_groups()

        if not self._groups_cache:
            self._current_group = None
            self.cbo_groups.addItem("(그룹 없음)", None)
            self.cbo_groups.setCurrentIndex(0)
            self.cbo_groups.blockSignals(False)

            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        for g in self._groups_cache:
            self.cbo_groups.addItem(g.name, g.id)

        target_id = select_group_id or (self._current_group.id if self._current_group else None)
        index_to_select = 0
        if target_id is not None:
            for i, g in enumerate(self._groups_cache):
                if g.id == target_id:
                    index_to_select = i
                    break

        self.cbo_groups.setCurrentIndex(index_to_select)
        self._current_group = self._groups_cache[index_to_select]
        self.cbo_groups.blockSignals(False)

        self._load_members(self._current_group.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    def _on_group_combo_changed(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._groups_cache):
            self._current_group = None
            self._load_members(None, self._member_keyword)
            self._load_candidates(self._candidate_keyword)
            return

        self._current_group = self._groups_cache[idx]
        self._load_members(self._current_group.id, self._member_keyword)
        self._load_candidates(self._candidate_keyword)

    # -----------------
    # Group CRUD popup
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
        self.reload_groups()

    # -----------------
    # Search / Load (Debounced + BG)
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
            return self.repo.search_contacts(kw)

        def done(rows: list[ContactRow]):
            self.candidates_model.setRowCount(0)

            for i, r in enumerate(rows, start=1):
                in_group = int(r.id) in self._member_id_set
                self.candidates_model.appendRow(self._contact_to_items(i, r, disabled=in_group))

            self.tbl_candidates.clearSelection()
            self._sync_header_by_selection(self.tbl_candidates)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

    def _load_members(self, group_id: int | None, keyword: str) -> None:
        gid = group_id
        kw = (keyword or "").strip().lower()

        def job():
            if not gid:
                return ([], set())
            all_members = self.repo.list_group_members(gid)
            id_set = {int(r.id) for r in all_members}
            return (all_members, id_set)

        def done(res):
            all_members, id_set = res
            self.members_model.setRowCount(0)
            self._member_id_set = set(id_set)

            if not gid:
                self.tbl_members.clearSelection()
                self._sync_header_by_selection(self.tbl_members)
                self._load_candidates(self._candidate_keyword)
                return

            def match(r: ContactRow) -> bool:
                if not kw:
                    return True
                hay = " ".join([
                    str(r.emp_id or ""), str(r.name or ""), str(r.phone or ""),
                    str(r.agency or ""), str(r.branch or "")
                ]).lower()
                return kw in hay

            shown = 0
            for r in all_members:
                if match(r):
                    shown += 1
                    self.members_model.appendRow(self._contact_to_items(shown, r, disabled=False))

            self.tbl_members.clearSelection()
            self._sync_header_by_selection(self.tbl_members)

            # 멤버 set이 바뀌면 후보 disable 상태 재계산 필요
            self._load_candidates(self._candidate_keyword)

        run_bg(job, on_done=done, on_error=lambda tb: QMessageBox.critical(self, "오류", tb))

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
    # Header 체크박스 = 전체 행 선택/해제
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
    def _contact_to_items(self, no: int, r: ContactRow, disabled: bool = False):
        no_item = QStandardItem(str(no))
        emp = QStandardItem(r.emp_id or "")
        name = QStandardItem(r.name or "")
        phone = QStandardItem(r.phone or "")
        agency = QStandardItem(r.agency or "")
        branch = QStandardItem(r.branch or "")
        hidden_id = QStandardItem(str(r.id))

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
