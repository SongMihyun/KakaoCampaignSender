# FILE: src/frontend/pages/contacts/import_preview_dialog.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTableView, QVBoxLayout


PreviewRow = Mapping[str, str] | Sequence[str]


class _PreviewModel(QAbstractTableModel):
    HEADERS = [
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
    KEYS = [
        "name",
        "customer_name",
        "customer_honorific",
        "customer_position",
        "agency",
        "branch",
        "phone",
        "customer_status",
        "tags",
        "memo2",
    ]

    def __init__(self, rows: Sequence[PreviewRow]) -> None:
        super().__init__()
        self._rows: list[PreviewRow] = list(rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None

        r = index.row()
        c = index.column()
        if r < 0 or r >= len(self._rows) or c < 0 or c >= len(self.KEYS):
            return None

        return self._value(self._rows[r], c)

    def _value(self, row: PreviewRow, column: int) -> str:
        if isinstance(row, Mapping):
            return str(row.get(self.KEYS[column], "") or "")
        try:
            value: Any = row[column]
        except Exception:
            value = ""
        return str(value or "")


class ImportPreviewDialog(QDialog):
    def __init__(self, rows: Sequence[PreviewRow], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("대상자 Import 미리보기")
        self.resize(1120, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("불러온 데이터를 확인한 뒤 저장을 진행합니다.")
        title.setStyleSheet("font-size:14px; font-weight:700;")
        root.addWidget(title)

        row_list = list(rows)
        sub = QLabel(f"총 {len(row_list)}건")
        sub.setStyleSheet("color:#6b7280;")
        root.addWidget(sub)

        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background:#ffffff;
                border:1px solid #e5e7eb;
                border-radius:12px;
            }
            """
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(12, 12, 12, 12)
        cv.setSpacing(8)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(False)

        self.model = _PreviewModel(row_list)
        self.table.setModel(self.model)

        widths = [170, 130, 80, 110, 150, 110, 140, 90, 120, 180]
        for idx, width in enumerate(widths):
            self.table.setColumnWidth(idx, width)

        cv.addWidget(self.table, 1)
        root.addWidget(card, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.btn_cancel = QPushButton("취소")
        self.btn_save = QPushButton("저장")

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.accept)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)
