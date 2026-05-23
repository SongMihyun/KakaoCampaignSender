# FILE: src/frontend/theme.py
from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QToolButton, QWidget

APP_STYLESHEET = """
QMainWindow { background: #f6f7f9; }

QWidget#AppHeader { background: transparent; border: none; }

QWidget#Card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}

QLabel#AppTitle { font-size: 16px; font-weight: 700; color: #111827; }
QLabel#SubTitle { font-size: 12px; color: #6b7280; }
QLabel#Meta { font-size: 11px; color: #9ca3af; }
QLabel#SectionTitle { font-size: 13px; font-weight: 600; color: #374151; }
QLabel#NavCaption {
    padding: 0 6px;
    font-size: 11px;
    font-weight: 700;
    color: #9ca3af;
}

QPushButton#TopNavButton {
    min-height: 30px;
    padding: 5px 14px;
    border-radius: 8px;
    border: 1px solid transparent;
    background: transparent;
    color: #4b5563;
    font-weight: 600;
}
QPushButton#TopNavButton:hover {
    background: #eef0f3;
    color: #111827;
}
QPushButton#TopNavButton:checked {
    background: #111827;
    color: #ffffff;
    border-color: #111827;
}

QListWidget#NavList {
    background: transparent;
    border: none;
    padding: 0;
    font-size: 13px;
    outline: none;
}
QListWidget#NavList::item {
    padding: 10px 12px;
    border-radius: 8px;
    margin: 1px 0;
    color: #4b5563;
}
QListWidget#NavList::item:selected {
    background: #111827;
    color: #ffffff;
    font-weight: 600;
}
QListWidget#NavList::item:hover:!selected { background: #e5e7eb; }

QWidget#Page {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}
QLabel#PageTitle { font-size: 17px; font-weight: 700; color: #111827; }
QLabel#PageDesc { font-size: 12px; color: #6b7280; padding-bottom: 2px; }

QPushButton {
    min-height: 30px;
    padding: 5px 12px;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    background: #ffffff;
    color: #374151;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover { background: #f9fafb; border-color: #9ca3af; }
QPushButton:pressed { background: #f3f4f6; }
QPushButton:disabled { background: #f9fafb; color: #9ca3af; border-color: #e5e7eb; }

QPushButton[btnRole="primary"] {
    background: #1f2937;
    border-color: #1f2937;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[btnRole="primary"]:hover { background: #111827; border-color: #111827; }
QPushButton[btnRole="primary"]:pressed { background: #030712; }
QPushButton[btnRole="primary"]:disabled { background: #9ca3af; border-color: #9ca3af; color: #f9fafb; }

QPushButton[btnRole="accent"] {
    background: #eef6ff;
    border-color: #bfdbfe;
    color: #1d4ed8;
    font-weight: 600;
}
QPushButton[btnRole="accent"]:hover { background: #dbeafe; border-color: #93c5fd; }

QPushButton[btnRole="danger"] {
    background: #ffffff;
    border-color: #fca5a5;
    color: #b91c1c;
}
QPushButton[btnRole="danger"]:hover { background: #fef2f2; border-color: #f87171; }

QPushButton[btnRole="ghost"] {
    background: transparent;
    border-color: transparent;
    color: #6b7280;
    min-height: 28px;
    padding: 4px 10px;
}
QPushButton[btnRole="ghost"]:hover { background: #f3f4f6; color: #374151; }

QPushButton[btnRole="icon"] {
    min-width: 34px;
    max-width: 34px;
    min-height: 30px;
    padding: 0;
    font-size: 12px;
}

QToolButton {
    min-height: 30px;
    padding: 5px 12px;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    background: #ffffff;
    color: #374151;
    font-size: 13px;
    font-weight: 500;
}
QToolButton:hover { background: #f9fafb; }
QToolButton[btnRole="secondary"] { border-color: #d1d5db; background: #f9fafb; }
QToolButton[btnRole="primary"] {
    background: #1f2937;
    border-color: #1f2937;
    color: #ffffff;
    font-weight: 600;
}
QToolButton[btnRole="ghost"] {
    background: transparent;
    border-color: transparent;
    color: #6b7280;
}
QToolButton[btnRole="danger"] {
    background: #ffffff;
    border-color: #fca5a5;
    color: #b91c1c;
}

QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit {
    min-height: 30px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 5px 10px;
    background: #ffffff;
    font-size: 13px;
    selection-background-color: #d1d5db;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
    border-color: #6b7280;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox#CampaignCombo, QComboBox#GroupCombo {
    padding-right: 58px;
}

QTableView {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    gridline-color: #f3f4f6;
    font-size: 13px;
    selection-background-color: #e5e7eb;
    selection-color: #111827;
}
QTableView::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #9ca3af;
    border-radius: 5px;
    background: #ffffff;
}
QTableView::indicator:hover {
    border-color: #6b7280;
}
QTableView::indicator:checked {
    background: #be185d;
    border-color: #be185d;
}
QTableView::indicator:checked:hover {
    background: #9d174d;
    border-color: #9d174d;
}
QHeaderView::section {
    background: #f9fafb;
    color: #4b5563;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    border-right: 1px solid #f3f4f6;
    font-weight: 600;
    font-size: 12px;
}

QListWidget {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    font-size: 13px;
}
QListWidget::item { padding: 8px 10px; border-radius: 6px; margin: 1px 4px; }
QListWidget::item:selected { background: #e5e7eb; color: #111827; }

QListWidget#CampaignItems {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    padding: 4px;
}
QListWidget#CampaignItems::item {
    padding: 0;
    margin: 2px;
    border-radius: 8px;
}
QListWidget#CampaignItems::item:selected {
    background: #eef0f3;
}
QWidget#CampaignItemRow {
    background: transparent;
}
QLabel#CampaignItemText {
    color: #111827;
    font-size: 13px;
}
QLabel#MutedText {
    color: #6b7280;
    font-size: 13px;
}
QLabel#CombinedPreviewLabel {
    padding: 10px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    background: #f9fafb;
    color: #111827;
    font-size: 13px;
    font-weight: 700;
}
QLabel#CampaignThumb {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    color: #6b7280;
    font-size: 10px;
}
QToolButton#InlineDeleteButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    border-radius: 14px;
    border: 1px solid transparent;
    background: transparent;
    color: #9ca3af;
    font-weight: 700;
}
QToolButton#InlineDeleteButton:hover {
    background: #fef2f2;
    border-color: #fecaca;
    color: #b91c1c;
}
QToolButton#CampaignComboDeleteButton, QToolButton#ComboDeleteButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    border-radius: 6px;
    border: 1px solid transparent;
    background: #f9fafb;
    color: #9ca3af;
    font-weight: 700;
}
QToolButton#CampaignComboDeleteButton:hover, QToolButton#ComboDeleteButton:hover {
    background: #fef2f2;
    border-color: #fecaca;
    color: #b91c1c;
}

QToolButton#HeaderMenuBtn {
    min-height: 30px;
    padding: 5px 14px;
    border-radius: 8px;
    border: 1px solid transparent;
    background: transparent;
    color: #4b5563;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#HeaderMenuBtn:hover {
    background: #eef0f3;
    color: #111827;
}

QFrame#SendModeSwitch {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}
QPushButton#SendModeButton {
    min-width: 48px;
    min-height: 28px;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid transparent;
    background: transparent;
    color: #4b5563;
    font-weight: 700;
}
QPushButton#SendModeButton:hover { background: #f9fafb; }
QPushButton#SendModeButton:checked {
    background: #1f2937;
    border-color: #1f2937;
    color: #ffffff;
}

QMenu {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 26px 7px 12px;
    border-radius: 6px;
    color: #374151;
}
QMenu::item:selected { background: #f3f4f6; color: #111827; }
QMenu::separator { height: 1px; background: #e5e7eb; margin: 6px 4px; }

QProgressBar {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: #f3f4f6;
}
QProgressBar::chunk {
    background: #1f2937;
    border-radius: 5px;
}
"""


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def style_button(btn: QPushButton, role: str = "secondary") -> QPushButton:
    btn.setProperty("btnRole", role)
    _repolish(btn)
    return btn


def style_tool_button(btn: QToolButton, role: str = "secondary") -> QToolButton:
    btn.setProperty("btnRole", role)
    _repolish(btn)
    return btn
