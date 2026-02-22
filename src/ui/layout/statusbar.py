from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt


class StatusBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self.message = QLabel("—")
        self.message.setObjectName("Meta")

        self.progress = QProgressBar()
        self.progress.setFixedHeight(14)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(260)

        layout.addWidget(self.message, 1)
        layout.addWidget(self.progress, 0, Qt.AlignRight)

    def set_message(self, text: str) -> None:
        self.message.setText(text)

    def set_progress(self, value: int) -> None:
        value = max(0, min(100, value))
        self.progress.setValue(value)
