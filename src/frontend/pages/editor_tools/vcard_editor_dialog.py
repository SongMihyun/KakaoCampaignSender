from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from backend.integrations.vcard_contacts import VCardContact, save_vcard_contacts
from backend.integrations.windows.win_file_picker import Filter, pick_save_file
from frontend.theme import style_button


class VCardContactsModel(QAbstractTableModel):
    HEADERS = ["", "No", "사번", "이름", "휴대폰", "보조 전화", "대리점명", "지사명"]

    def __init__(self, contacts: list[VCardContact] | None = None) -> None:
        super().__init__()
        self._rows = list(contacts or [])
        self._checked: set[int] = set()

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
        row = index.row()
        col = index.column()
        contact = self._rows[row]

        if col == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if row in self._checked else Qt.Unchecked

        if row in self._checked:
            if role == Qt.BackgroundRole:
                return QColor("#e5e7eb")
            if role == Qt.FontRole:
                font = QFont()
                font.setWeight(QFont.Medium)
                return font

        if role == Qt.DisplayRole:
            return self._value(contact, row, col)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        if index.column() == 0 and role == Qt.CheckStateRole:
            row = index.row()
            if value == Qt.Checked:
                self._checked.add(row)
            else:
                self._checked.discard(row)
            self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
            return True
        return False

    def contacts(self) -> list[VCardContact]:
        return list(self._rows)

    def contact_at(self, row: int) -> VCardContact:
        return self._rows[row]

    def add_contact(self, contact: VCardContact) -> None:
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(contact)
        self.endInsertRows()

    def update_contact(self, row: int, contact: VCardContact) -> None:
        self._rows[row] = contact
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))

    def delete_checked(self) -> int:
        rows = sorted(self._checked, reverse=True)
        for row in rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._rows[row]
            self.endRemoveRows()
        self._checked.clear()
        return len(rows)

    def checked_rows(self) -> list[int]:
        return sorted(self._checked)

    @staticmethod
    def _value(contact: VCardContact, row: int, col: int) -> str | int:
        if col == 1:
            return row + 1
        if col == 2:
            return contact.emp_id
        if col == 3:
            return contact.name
        if col == 4:
            return contact.phone
        if col == 5:
            return contact.phone_alt
        if col == 6:
            return contact.agency
        if col == 7:
            return contact.branch
        return ""


class VCardContactDialog(QDialog):
    def __init__(self, *, title: str, contact: VCardContact | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)

        form = QVBoxLayout(self)
        form.setSpacing(8)

        self.emp_id = QLineEdit()
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.phone_alt = QLineEdit()
        self.agency = QLineEdit()
        self.branch = QLineEdit()

        fields = [
            ("사번", self.emp_id),
            ("이름", self.name),
            ("휴대폰", self.phone),
            ("보조 전화", self.phone_alt),
            ("대리점명", self.agency),
            ("지사명", self.branch),
        ]
        for label, editor in fields:
            form.addWidget(QLabel(label))
            form.addWidget(editor)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = style_button(QPushButton("취소"), "secondary")
        btn_ok = style_button(QPushButton("저장"), "primary")
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        form.addLayout(buttons)

        if contact:
            self.emp_id.setText(contact.emp_id)
            self.name.setText(contact.name)
            self.phone.setText(contact.phone)
            self.phone_alt.setText(contact.phone_alt)
            self.agency.setText(contact.agency)
            self.branch.setText(contact.branch)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._accept_if_valid)
        self.name.returnPressed.connect(self._accept_if_valid)

    def _accept_if_valid(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "입력 확인", "이름은 필수입니다.")
            return
        self.accept()

    def contact(self) -> VCardContact:
        return VCardContact(
            emp_id=self.emp_id.text().strip(),
            name=self.name.text().strip(),
            phone=self.phone.text().strip(),
            phone_alt=self.phone_alt.text().strip(),
            agency=self.agency.text().strip(),
            branch=self.branch.text().strip(),
        )


class VCardEditorDialog(QDialog):
    def __init__(self, *, path: str, contacts: list[VCardContact], parent=None) -> None:
        super().__init__(parent)
        self._path = str(path)
        self.setWindowTitle(f"VCF 연락처 편집 - {Path(path).name}")
        self.resize(980, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("VCF 연락처 편집")
        title.setObjectName("PageTitle")
        subtitle = QLabel(f"- {Path(path).name} · {len(contacts)}건")
        subtitle.setObjectName("PageDesc")
        title_row.addWidget(title)
        title_row.addWidget(subtitle)
        title_row.addStretch(1)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.btn_add = style_button(QPushButton("추가"), "primary")
        self.btn_edit = style_button(QPushButton("선택 수정"), "secondary")
        self.btn_delete = style_button(QPushButton("선택 삭제"), "danger")
        self.btn_save = style_button(QPushButton("저장"), "primary")
        self.btn_save_as = style_button(QPushButton("다른 이름 저장"), "secondary")
        self.btn_close = style_button(QPushButton("닫기"), "secondary")
        action_row.addWidget(self.btn_add)
        action_row.addWidget(self.btn_edit)
        action_row.addWidget(self.btn_delete)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_save)
        action_row.addWidget(self.btn_save_as)
        action_row.addWidget(self.btn_close)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.model = VCardContactsModel(contacts)
        self.table.setModel(self.model)
        self._apply_column_widths()

        layout.addLayout(title_row)
        layout.addLayout(action_row)
        layout.addWidget(self.table, 1)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_delete.clicked.connect(self._delete_checked)
        self.btn_save.clicked.connect(lambda: self._save(self._path))
        self.btn_save_as.clicked.connect(self._save_as)
        self.btn_close.clicked.connect(self.accept)
        self.table.doubleClicked.connect(lambda _idx: self._edit_selected())

    def _apply_column_widths(self) -> None:
        for col, width in {0: 42, 1: 56, 2: 120, 3: 220, 4: 150, 5: 150, 6: 150, 7: 150}.items():
            self.table.setColumnWidth(col, width)

    def _selected_row(self) -> int:
        selected = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return selected[0].row() if selected else -1

    def _add(self) -> None:
        dlg = VCardContactDialog(title="연락처 추가", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.model.add_contact(dlg.contact())

    def _edit_selected(self) -> None:
        row = self._selected_row()
        if row < 0:
            checked = self.model.checked_rows()
            row = checked[0] if len(checked) == 1 else -1
        if row < 0:
            QMessageBox.information(self, "안내", "수정할 연락처 1건을 선택하세요.")
            return
        dlg = VCardContactDialog(title="연락처 수정", contact=self.model.contact_at(row), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.model.update_contact(row, dlg.contact())

    def _delete_checked(self) -> None:
        count = len(self.model.checked_rows())
        if count <= 0:
            QMessageBox.information(self, "안내", "삭제할 연락처를 체크하세요.")
            return
        if QMessageBox.question(self, "삭제 확인", f"{count}건을 삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.delete_checked()

    def _save_as(self) -> None:
        path = pick_save_file(
            title="VCF 저장 위치 선택",
            filters=[Filter("vCard Files", "*.vcf"), Filter("All Files", "*.*")],
            default_ext="vcf",
            default_filename=Path(self._path).name,
        )
        if path:
            self._save(path)

    def _save(self, path: str) -> None:
        try:
            save_vcard_contacts(path, self.model.contacts())
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))
            return
        self._path = path
        QMessageBox.information(self, "저장 완료", f"저장했습니다.\n\n{path}")
