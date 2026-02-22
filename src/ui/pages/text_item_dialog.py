from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox
)


class TextItemDialog(QDialog):
    def __init__(self, title: str = "문구", text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(QLabel("문구"))
        self.ed_text = QTextEdit()
        self.ed_text.setPlaceholderText("캠페인에 넣을 문구를 입력하세요.")
        self.ed_text.setMinimumHeight(220)
        self.ed_text.setPlainText(text or "")
        root.addWidget(self.ed_text, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("확인")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

    def _on_ok(self) -> None:
        # 빈 문구 허용 여부는 정책에 따라 변경 가능 (현재는 허용 X)
        text = (self.ed_text.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "검증", "문구를 입력하세요.")
            return
        self.accept()

    def get_text(self) -> str:
        return (self.ed_text.toPlainText() or "").strip()
