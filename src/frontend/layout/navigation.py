from PySide6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal


class Navigation(QWidget):
    page_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.list = QListWidget()
        self.list.setObjectName("NavList")
        self.list.setFixedWidth(220)

        # ✅ 메뉴 5개 (스택 인덱스와 1:1 매칭)
        self._items = ["대상자", "그룹관리", "캠페인", "발송", "로그"]

        for name in self._items:
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.list.addItem(item)

        self.list.currentRowChanged.connect(self.page_changed.emit)

    def build_layout(self, stack) -> QHBoxLayout:
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(10)
        wrap.addWidget(self.list)
        wrap.addWidget(stack, 1)
        return wrap

    def set_current(self, idx: int) -> None:
        if 0 <= idx < self.list.count():
            self.list.setCurrentRow(idx)
