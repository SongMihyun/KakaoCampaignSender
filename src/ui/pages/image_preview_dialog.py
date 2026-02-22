from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout


class ImagePreviewDialog(QDialog):
    def __init__(self, title: str, image_bytes: bytes, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 420)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("""
            QLabel { background:#f9fafb; border:1px dashed #d1d5db; border-radius:12px; }
        """)
        root.addWidget(self.lbl, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_ok = QPushButton("닫기")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

        pix = QPixmap()
        if pix.loadFromData(image_bytes or b""):
            self._pix = pix
            self._render()
        else:
            self.lbl.setText("이미지를 불러올 수 없습니다.")
            self._pix = QPixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        if self._pix.isNull():
            return
        scaled = self._pix.scaled(self.lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl.setPixmap(scaled)
