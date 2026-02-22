from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from datetime import datetime


class Header(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(4)

        self.title = QLabel("Campaign Sender")
        self.title.setObjectName("AppTitle")

        self.subtitle = QLabel("—")
        self.subtitle.setObjectName("SubTitle")

        left.addWidget(self.title)
        left.addWidget(self.subtitle)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignRight)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.meta = QLabel(f"Local | {now}")
        self.meta.setObjectName("Meta")

        self.env = QLabel("Env: Poetry .venv")
        self.env.setObjectName("Meta")

        right.addWidget(self.meta)
        right.addWidget(self.env)

        layout.addLayout(left, 1)
        layout.addLayout(right)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
