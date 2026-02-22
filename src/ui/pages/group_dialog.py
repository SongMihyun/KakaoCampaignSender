from __future__ import annotations

from typing import Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QMessageBox
)


class GroupDialog(QDialog):
    """
    그룹 생성/수정 공용 다이얼로그
    - get_data() -> {"name": str, "memo": str}
    """
    def __init__(self, title: str, preset: Optional[Dict[str, str]] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(QLabel("그룹명"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("예) VIP_2월_프로모션")
        root.addWidget(self.ed_name)

        root.addWidget(QLabel("메모"))
        self.ed_memo = QTextEdit()
        self.ed_memo.setPlaceholderText("그룹 설명/기준 등을 기록하세요.")
        self.ed_memo.setFixedHeight(120)
        root.addWidget(self.ed_memo)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        if preset:
            self.ed_name.setText(preset.get("name", ""))
            self.ed_memo.setPlainText(preset.get("memo", ""))

    def _on_ok(self) -> None:
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "검증", "그룹명은 필수입니다.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.ed_name.text().strip(),
            "memo": self.ed_memo.toPlainText().strip(),
        }
