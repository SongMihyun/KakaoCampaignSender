from __future__ import annotations

from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHeaderView, QStyle, QStyleOptionButton, QStyleOptionHeader


class CheckableHeader(QHeaderView):
    toggled = Signal(bool)

    def __init__(self, orientation: Qt.Orientation, parent=None, check_col: int = 0):
        super().__init__(orientation, parent)
        self._check_state: Qt.CheckState = Qt.Unchecked
        self._check_col = check_col
        self.setSectionsClickable(True)

        # 체크박스/텍스트 간격
        self._margin_left = 8
        self._gap = 6

    def set_check_state(self, state: Qt.CheckState) -> None:
        self._check_state = state
        self.viewport().update()

    def _indicator_rect(self, section_rect: QRect) -> QRect:
        opt = QStyleOptionButton()
        indicator = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, opt, self)
        x = section_rect.left() + self._margin_left
        y = section_rect.center().y() - indicator.height() // 2
        return QRect(x, y, indicator.width(), indicator.height())

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int) -> None:
        # 체크 컬럼 아니면 기본 처리
        if logicalIndex != self._check_col:
            super().paintSection(painter, rect, logicalIndex)
            return

        painter.save()

        # 1) 헤더 기본(배경/보더/정렬 표시 포함) + 텍스트는 "No" 유지
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logicalIndex

        # 기존 headerData에서 가져온 텍스트 유지 (QStandardItemModel의 라벨이 들어감)
        # 다만 체크박스가 그려질 공간 확보 위해 텍스트 위치를 오른쪽으로 살짝 민다
        cb_rect = self._indicator_rect(rect)
        opt.text = opt.text or ""
        # 기본 헤더를 먼저 그림(텍스트 포함)
        self.style().drawControl(QStyle.CE_Header, opt, painter, self)

        # 2) 체크박스 그리기
        cbopt = QStyleOptionButton()
        cbopt.rect = cb_rect
        if self._check_state == Qt.Checked:
            cbopt.state = QStyle.State_Enabled | QStyle.State_On
        elif self._check_state == Qt.PartiallyChecked:
            cbopt.state = QStyle.State_Enabled | QStyle.State_NoChange
        else:
            cbopt.state = QStyle.State_Enabled | QStyle.State_Off

        self.style().drawControl(QStyle.CE_CheckBox, cbopt, painter, self)

        # 3) 텍스트가 체크박스에 가리지 않도록(겹침 방지) 텍스트만 다시 한번 오른쪽으로 그려줌
        #    (플랫폼 스타일별로 CE_Header 텍스트 위치가 달라서 안전하게 오버드로우)
        text_rect = QRect(
            cb_rect.right() + self._gap,
            rect.top(),
            rect.width() - (cb_rect.width() + self._margin_left + self._gap),
            rect.height(),
        )
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, opt.text)

        painter.restore()

    def mousePressEvent(self, event) -> None:
        idx = self.logicalIndexAt(event.pos())
        if idx == self._check_col:
            x = self.sectionViewportPosition(idx)
            w = self.sectionSize(idx)
            section_rect = QRect(x, 0, w, self.height())
            cb_rect = self._indicator_rect(section_rect)

            if cb_rect.contains(event.pos()):
                new_checked = (self._check_state != Qt.Checked)
                self._check_state = Qt.Checked if new_checked else Qt.Unchecked
                self.viewport().update()
                self.toggled.emit(new_checked)
                event.accept()
                return

        super().mousePressEvent(event)
