# FILE: src/frontend/theme.py
from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QToolButton, QWidget

APP_STYLESHEET = """
QMainWindow { background: #f3f4f6; }

QWidget#Card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}

QLabel#AppTitle { font-size: 17px; font-weight: 700; color: #111827; }
QLabel#SubTitle { font-size: 12px; color: #6b7280; }
QLabel#Meta { font-size: 11px; color: #9ca3af; }
QLabel#SectionTitle { font-size: 13px; font-weight: 600; color: #374151; }

QListWidget#NavList {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 4px;
    font-size: 13px;
    outline: none;
}
QListWidget#NavList::item {
    padding: 11px 14px;
    border-radius: 8px;
    margin: 2px 0;
    color: #374151;
}
QListWidget#NavList::item:selected {
    background: #eff6ff;
    color: #1d4ed8;
    font-weight: 600;
}
QListWidget#NavList::item:hover:!selected {
    background: #f9fafb;
}

QWidget#Page {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}
QLabel#PageTitle { font-size: 17px; font-weight: 700; color: #111827; }
QLabel#PageDesc { font-size: 12px; color: #6b7280; padding-bottom: 2px; }

QPushButton {
    min-height: 32px;
    padding: 6px 14px;
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
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[btnRole="primary"]:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton[btnRole="primary"]:pressed { background: #1e40af; }
QPushButton[btnRole="primary"]:disabled { background: #93c5fd; border-color: #93c5fd; color: #eff6ff; }

QPushButton[btnRole="accent"] {
    background: #0ea5e9;
    border-color: #0ea5e9;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[btnRole="accent"]:hover { background: #0284c7; border-color: #0284c7; }

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
    min-width: 36px;
    max-width: 36px;
    min-height: 32px;
    padding: 0;
    font-size: 12px;
}

QToolButton {
    min-height: 32px;
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    background: #ffffff;
    color: #374151;
    font-size: 13px;
    font-weight: 500;
}
QToolButton:hover { background: #f9fafb; }
QToolButton[btnRole="secondary"] {
    border-color: #d1d5db;
    background: #f9fafb;
}

QLineEdit, QTextEdit, QComboBox, QSpinBox {
    min-height: 32px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 6px 10px;
    background: #ffffff;
    font-size: 13px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #60a5fa;
}
QComboBox::drop-down { border: none; width: 24px; }

QTableView {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    gridline-color: #f3f4f6;
    font-size: 13px;
    selection-background-color: #dbeafe;
    selection-color: #111827;
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
QListWidget::item:selected { background: #eff6ff; color: #1e3a8a; }

QToolButton#HeaderMenuBtn {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    font-size: 15px;
}
QToolButton#HeaderMenuBtn:hover { background: #f9fafb; }

QProgressBar {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: #f3f4f6;
}
QProgressBar::chunk {
    background: #2563eb;
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
