# FILE: src/frontend/theme.py
from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QToolButton, QWidget

APP_STYLESHEET = """
QMainWindow { background: #06070a; }

QWidget#AppHeader { background: transparent; border: none; }

QWidget#Card {
    background: #1c212c;
    border: 1px solid rgba(255, 255, 255, 36);
    border-radius: 12px;
}

QLabel#AppTitle { font-size: 16px; font-weight: 700; color: #f2f4f7; }
QLabel#SubTitle { font-size: 12px; color: #8b93a1; }
QLabel#Meta { font-size: 11px; color: #6d7686; }
QLabel#SectionTitle { font-size: 13px; font-weight: 600; color: #c7cbd3; }
QLabel#NavCaption {
    padding: 0 6px;
    font-size: 11px;
    font-weight: 700;
    color: #6d7686;
}

QPushButton#TopNavButton {
    min-height: 30px;
    padding: 5px 14px;
    border-radius: 9px;
    border: 1px solid transparent;
    background: transparent;
    color: #9aa0ab;
    font-weight: 600;
}
QPushButton#TopNavButton:hover {
    background: rgba(255, 255, 255, 18);
    color: #f2f4f7;
}
QPushButton#TopNavButton:checked {
    background: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
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
    border-radius: 9px;
    margin: 1px 0;
    color: #9aa0ab;
}
QListWidget#NavList::item:selected {
    background: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QListWidget#NavList::item:hover:!selected { background: rgba(255, 255, 255, 18); color: #e8eaed; }

QWidget#Page {
    background: #15181f;
    border: 1px solid rgba(255, 255, 255, 32);
    border-radius: 16px;
}
QLabel#PageTitle { font-size: 17px; font-weight: 700; color: #f2f4f7; }
QLabel#PageDesc { font-size: 12px; color: #8b93a1; padding-bottom: 2px; }

QPushButton {
    min-height: 30px;
    padding: 5px 12px;
    border-radius: 9px;
    border: 1px solid rgba(255, 255, 255, 26);
    background: rgba(255, 255, 255, 10);
    color: #d7dae0;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover { background: rgba(255, 255, 255, 20); border-color: rgba(255, 255, 255, 46); }
QPushButton:pressed { background: rgba(255, 255, 255, 6); }
QPushButton:disabled { background: rgba(255, 255, 255, 6); color: #5b6270; border-color: rgba(255, 255, 255, 14); }

QPushButton[btnRole="primary"] {
    background: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[btnRole="primary"]:hover { background: #2f6fe0; border-color: #2f6fe0; }
QPushButton[btnRole="primary"]:pressed { background: #2559ba; border-color: #2559ba; }
QPushButton[btnRole="primary"]:disabled { background: #35405a; border-color: #35405a; color: #8a93a8; }

QPushButton[btnRole="accent"] {
    background: rgba(59, 130, 246, 30);
    border-color: rgba(59, 130, 246, 120);
    color: #93c5fd;
    font-weight: 600;
}
QPushButton[btnRole="accent"]:hover { background: rgba(59, 130, 246, 46); border-color: rgba(59, 130, 246, 160); }

QPushButton[btnRole="danger"] {
    background: rgba(248, 113, 113, 16);
    border-color: rgba(248, 113, 113, 110);
    color: #fca5a5;
}
QPushButton[btnRole="danger"]:hover { background: rgba(248, 113, 113, 30); border-color: rgba(248, 113, 113, 160); }

QPushButton[btnRole="ghost"] {
    background: transparent;
    border-color: transparent;
    color: #8b93a1;
    min-height: 28px;
    padding: 4px 10px;
}
QPushButton[btnRole="ghost"]:hover { background: rgba(255, 255, 255, 16); color: #e8eaed; }

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
    border-radius: 9px;
    border: 1px solid rgba(255, 255, 255, 26);
    background: rgba(255, 255, 255, 10);
    color: #d7dae0;
    font-size: 13px;
    font-weight: 500;
}
QToolButton:hover { background: rgba(255, 255, 255, 20); }
QToolButton[btnRole="secondary"] { border-color: rgba(255, 255, 255, 26); background: rgba(255, 255, 255, 8); }
QToolButton[btnRole="primary"] {
    background: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QToolButton[btnRole="ghost"] {
    background: transparent;
    border-color: transparent;
    color: #8b93a1;
}
QToolButton[btnRole="danger"] {
    background: rgba(248, 113, 113, 16);
    border-color: rgba(248, 113, 113, 110);
    color: #fca5a5;
}

QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit {
    min-height: 30px;
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 9px;
    padding: 5px 10px;
    background: #0f1218;
    color: #e8eaed;
    font-size: 13px;
    selection-background-color: rgba(59, 130, 246, 90);
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox#CampaignCombo, QComboBox#GroupCombo {
    padding-right: 58px;
}
QComboBox QAbstractItemView {
    background: #191d26;
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 9px;
    color: #e8eaed;
    selection-background-color: rgba(59, 130, 246, 60);
    selection-color: #ffffff;
    outline: none;
}

QTableView {
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px;
    background: #15181f;
    alternate-background-color: #191d26;
    gridline-color: rgba(255, 255, 255, 10);
    color: #e8eaed;
    font-size: 13px;
    selection-background-color: rgba(59, 130, 246, 46);
    selection-color: #ffffff;
}
QTableView::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid rgba(255, 255, 255, 46);
    border-radius: 5px;
    background: #0f1218;
}
QTableView::indicator:hover {
    border-color: rgba(255, 255, 255, 90);
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
    background: #1c212c;
    color: #9aa0ab;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 20);
    border-right: 1px solid rgba(255, 255, 255, 10);
    font-weight: 600;
    font-size: 12px;
}

QListWidget {
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px;
    background: #15181f;
    color: #e8eaed;
    font-size: 13px;
}
QListWidget::item { padding: 8px 10px; border-radius: 7px; margin: 1px 4px; }
QListWidget::item:selected { background: rgba(255, 255, 255, 26); color: #f2f4f7; }

QListWidget#CampaignItems {
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px;
    background: #15181f;
    padding: 4px;
}
QListWidget#CampaignItems::item {
    padding: 0;
    margin: 2px;
    border-radius: 9px;
}
QListWidget#CampaignItems::item:selected {
    background: rgba(59, 130, 246, 30);
}
QWidget#CampaignItemRow {
    background: transparent;
}
QLabel#CampaignItemText {
    color: #e8eaed;
    font-size: 13px;
}
QLabel#MutedText {
    color: #8b93a1;
    font-size: 13px;
}
QLabel#CombinedPreviewLabel {
    padding: 10px 12px;
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 9px;
    background: #1c212c;
    color: #f2f4f7;
    font-size: 13px;
    font-weight: 700;
}
QLabel#CampaignThumb {
    background: #1c2029;
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 7px;
    color: #8b93a1;
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
    color: #6d7686;
    font-weight: 700;
}
QToolButton#InlineDeleteButton:hover {
    background: rgba(248, 113, 113, 24);
    border-color: rgba(248, 113, 113, 110);
    color: #fca5a5;
}
QToolButton#CampaignComboDeleteButton, QToolButton#ComboDeleteButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    border-radius: 7px;
    border: 1px solid transparent;
    background: rgba(255, 255, 255, 10);
    color: #6d7686;
    font-weight: 700;
}
QToolButton#CampaignComboDeleteButton:hover, QToolButton#ComboDeleteButton:hover {
    background: rgba(248, 113, 113, 24);
    border-color: rgba(248, 113, 113, 110);
    color: #fca5a5;
}

QToolButton#HeaderMenuBtn {
    min-height: 30px;
    padding: 5px 14px;
    border-radius: 9px;
    border: 1px solid transparent;
    background: transparent;
    color: #9aa0ab;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#HeaderMenuBtn:hover {
    background: rgba(255, 255, 255, 18);
    color: #f2f4f7;
}

QFrame#SendModeSwitch {
    background: #15181f;
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 9px;
}
QPushButton#SendModeButton {
    min-width: 48px;
    min-height: 28px;
    padding: 4px 10px;
    border-radius: 7px;
    border: 1px solid transparent;
    background: transparent;
    color: #9aa0ab;
    font-weight: 700;
}
QPushButton#SendModeButton:hover { background: rgba(255, 255, 255, 16); }
QPushButton#SendModeButton:checked {
    background: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
}

QMenu {
    background: #191d26;
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 12px;
    padding: 6px;
    color: #d7dae0;
}
QMenu::item {
    padding: 7px 26px 7px 12px;
    border-radius: 7px;
    color: #d7dae0;
}
QMenu::item:selected { background: rgba(255, 255, 255, 20); color: #f2f4f7; }
QMenu::separator { height: 1px; background: rgba(255, 255, 255, 20); margin: 6px 4px; }

QProgressBar {
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 7px;
    background: #1c212c;
    color: transparent;
}
QProgressBar::chunk {
    background: #3b82f6;
    border-radius: 6px;
}

QDialog { background: #15181f; color: #e8eaed; }
QMessageBox { background: #15181f; }
QLabel { color: #d7dae0; }
QCheckBox, QRadioButton { color: #d7dae0; spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid rgba(255, 255, 255, 46);
    border-radius: 4px;
    background: #0f1218;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
}
QToolTip {
    background: #191d26;
    color: #e8eaed;
    border: 1px solid rgba(255, 255, 255, 26);
    padding: 4px 8px;
    border-radius: 6px;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 46);
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 80); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 46);
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 80); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
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
