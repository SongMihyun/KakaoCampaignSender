from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)


class CampaignNameDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("캠페인 저장")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(QLabel("캠페인명"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("예) 2026_02_프로모션_A")
        root.addWidget(self.ed_name)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

    def _on_ok(self) -> None:
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "검증", "캠페인명은 필수입니다.")
            return
        self.accept()

    def get_name(self) -> str:
        return (self.ed_name.text() or "").strip()
