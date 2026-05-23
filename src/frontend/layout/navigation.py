from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class Navigation(QWidget):
    page_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        self.caption = QLabel("작업 메뉴")
        self.caption.setObjectName("NavCaption")

        self.list = QListWidget()
        self.list.setObjectName("NavList")
        self.list.setFixedWidth(154)

        self._items = ["대상자", "그룹", "캠페인", "발송", "로그"]

        for name in self._items:
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.list.addItem(item)

        self.list.currentRowChanged.connect(self.page_changed.emit)

    def build_layout(self, stack) -> QHBoxLayout:
        side = QWidget()
        side.setObjectName("SideNav")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(8)
        side_layout.addWidget(self.caption)
        side_layout.addWidget(self.list, 1)

        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(12)
        wrap.addWidget(side)
        wrap.addWidget(stack, 1)
        return wrap

    def set_current(self, idx: int) -> None:
        if 0 <= idx < self.list.count():
            self.list.setCurrentRow(idx)
