# src/ui/pages/import_preview_dialog.py
from __future__ import annotations

from typing import List, Sequence, Tuple

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableView,
    QHBoxLayout, QPushButton, QFrame
)


PreviewRow = Tuple[str, str, str, str, str]  # (emp_id, name, phone, agency, branch)


class _PreviewModel(QAbstractTableModel):
    HEADERS = ["사번", "이름", "전화", "대리점", "지사"]

    def __init__(self, rows: Sequence[PreviewRow]) -> None:
        super().__init__()
        self._rows: List[PreviewRow] = list(rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 5

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None

        r = index.row()
        c = index.column()
        if r < 0 or r >= len(self._rows):
            return None

        return self._rows[r][c]


class ImportPreviewDialog(QDialog):
    """
    엑셀 Import 미리보기:
    - 저장 누르면 accept()
    - 취소 누르면 reject()
    """

    def __init__(self, rows: Sequence[PreviewRow], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("엑셀 Import 미리보기")
        self.resize(920, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("불러온 데이터를 확인한 뒤 저장을 진행합니다.")
        title.setStyleSheet("font-size:14px; font-weight:700;")
        root.addWidget(title)

        sub = QLabel(f"총 {len(list(rows))}건")
        sub.setStyleSheet("color:#6b7280;")
        root.addWidget(sub)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background:#ffffff;
                border:1px solid #e5e7eb;
                border-radius:12px;
            }
        """)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(12, 12, 12, 12)
        cv.setSpacing(8)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(False)

        self.model = _PreviewModel(rows)
        self.table.setModel(self.model)

        # 컬럼 폭(가독성)
        self.table.setColumnWidth(0, 120)  # 사번
        self.table.setColumnWidth(1, 140)  # 이름
        self.table.setColumnWidth(2, 160)  # 전화
        self.table.setColumnWidth(3, 200)  # 대리점
        self.table.setColumnWidth(4, 200)  # 지사

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
