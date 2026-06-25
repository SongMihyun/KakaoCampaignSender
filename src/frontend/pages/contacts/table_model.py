# FILE: src/frontend/pages/contacts/table_model.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont


@dataclass
class Contact:
    id: int
    emp_id: str
    name: str
    customer_name: str = ""
    customer_honorific: str = "고객님"
    customer_position: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    customer_status: str = ""
    tags: str = ""
    memo2: str = ""
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None


class ContactsTableModel(QAbstractTableModel):
    HEADERS = [
        "",
        "No",
        "카카오톡 검색명",
        "고객명",
        "호칭",
        "직책",
        "소속/대리점",
        "지사",
        "연락처",
        "상태",
        "태그",
        "메모",
    ]

    def __init__(self, rows: list[Contact] | None = None):
        super().__init__()
        self._rows: list[Contact] = rows or []
        self._checked_ids: set[int] = set()

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

        if c == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if item.id in self._checked_ids else Qt.Unchecked

        if item.id in self._checked_ids:
            if role == Qt.BackgroundRole:
                return QColor("#e5e7eb")
            if role == Qt.FontRole:
                font = QFont()
                font.setWeight(QFont.Medium)
                return font

        if role == Qt.DisplayRole:
            if c == 1:
                return r + 1
            if c == 2:
                return item.name
            if c == 3:
                return item.customer_name or item.name
            if c == 4:
                return item.customer_honorific or "고객님"
            if c == 5:
                return item.customer_position
            if c == 6:
                return item.agency
            if c == 7:
                return item.branch
            if c == 8:
                return item.phone
            if c == 9:
                return item.customer_status
            if c == 10:
                return item.tags
            if c == 11:
                return item.memo2

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        if index.column() == 0 and role == Qt.CheckStateRole:
            item = self._rows[index.row()]
            if value == Qt.Checked:
                self._checked_ids.add(item.id)
            else:
                self._checked_ids.discard(item.id)
            left = self.index(index.row(), 0)
            right = self.index(index.row(), self.columnCount() - 1)
            self.dataChanged.emit(left, right, [Qt.CheckStateRole, Qt.BackgroundRole, Qt.FontRole])
            return True

        return False

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
        valid_ids = {c.id for c in self._rows}
        self._checked_ids = {i for i in self._checked_ids if i in valid_ids}
        self.endResetModel()

    def add_contact(self, c: Contact) -> None:
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(c)
        self.endInsertRows()
