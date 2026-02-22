# src/ui/pages/contacts_model.py
from __future__ import annotations
from dataclasses import dataclass

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex


@dataclass
class Contact:
    id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str


class ContactsTableModel(QAbstractTableModel):
    HEADERS = ["", "No", "사번", "이름", "전화번호", "대리점명", "지사명"]

    def __init__(self, rows: list[Contact] | None = None):
        super().__init__()
        self._rows: list[Contact] = rows or []
        self._checked_ids: set[int] = set()

    # ---------- basic ----------
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        r = index.row()
        c = index.column()
        item = self._rows[r]

        # 체크박스
        if c == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if item.id in self._checked_ids else Qt.Unchecked

        if role == Qt.DisplayRole:
            if c == 1:  # 순번 (1부터)
                return r + 1
            if c == 2:
                return item.emp_id
            if c == 3:
                return item.name
            if c == 4:
                return item.phone
            if c == 5:
                return item.agency
            if c == 6:
                return item.branch

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable

        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        # ✅ 사번(2)만 인라인 편집 허용
        if index.column() == 2:
            return base | Qt.ItemIsEditable

        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        r = index.row()
        c = index.column()

        # 체크박스
        if c == 0 and role == Qt.CheckStateRole:
            item = self._rows[r]
            if value == Qt.Checked:
                self._checked_ids.add(item.id)
            else:
                self._checked_ids.discard(item.id)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True

        # ✅ 사번 편집: "빈값 허용 + 값 있을 때만 중복 금지"
        if c == 2 and role in (Qt.EditRole, Qt.DisplayRole):
            item = self._rows[r]
            new_emp_id = (str(value) if value is not None else "").strip()

            # 1) 빈값 허용
            if new_emp_id == "":
                if item.emp_id != "":
                    item.emp_id = ""
                    self.dataChanged.emit(index, index, [Qt.DisplayRole])
                return True

            # 2) 값이 있으면 중복 금지(본인 행 제외)
            for i, other in enumerate(self._rows):
                if i == r:
                    continue
                if (other.emp_id or "").strip() == new_emp_id:
                    return False  # 중복 -> 반영 안 함(사용자 경험은 Page에서 DB검증/롤백으로 보완)

            # 3) 적용
            if item.emp_id != new_emp_id:
                item.emp_id = new_emp_id
                self.dataChanged.emit(index, index, [Qt.DisplayRole])
            return True

        return False

    # ---------- helpers ----------
    def contact_at(self, row: int) -> Contact:
        return self._rows[row]

    def checked_ids(self) -> list[int]:
        return sorted(self._checked_ids)

    def set_checked_ids(self, ids: list[int]) -> None:
        self._checked_ids = set(ids)
        self.layoutChanged.emit()

    def clear_checked(self) -> None:
        self._checked_ids.clear()
        self.layoutChanged.emit()

    def reset_rows(self, rows: list[Contact]) -> None:
        self.beginResetModel()
        self._rows = rows

        # 존재하지 않는 id 체크 제거
        valid_ids = {c.id for c in self._rows}
        self._checked_ids = {i for i in self._checked_ids if i in valid_ids}

        self.endResetModel()

    def add_contact(self, c: Contact) -> None:
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(c)
        self.endInsertRows()
