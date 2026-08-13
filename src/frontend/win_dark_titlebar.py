# FILE: src/frontend/win_dark_titlebar.py
from __future__ import annotations

import ctypes
from typing import Optional

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget


def apply_dark_titlebar(hwnd: int) -> None:
    """Windows 10 1809+/11: 네이티브 타이틀바를 다크 모드로 칠한다(실패해도 무해)."""
    try:
        value = ctypes.c_int(1)
        for attr in (20, 19):  # 20 = 최신, 19 = 구형 Windows 10 빌드용 fallback
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(int(hwnd)), attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if res == 0:
                break
    except Exception:
        pass


class _DarkTitlebarEventFilter(QObject):
    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            try:
                apply_dark_titlebar(int(obj.winId()))
            except Exception:
                pass
        return False


_filter_instance: Optional[_DarkTitlebarEventFilter] = None


def install_dark_titlebar_for_all_windows(app: QApplication) -> None:
    """앱 전체의 모든 최상위 창(다이얼로그 포함)에 다크 타이틀바를 자동 적용한다."""
    global _filter_instance
    if _filter_instance is not None:
        return
    _filter_instance = _DarkTitlebarEventFilter()
    app.installEventFilter(_filter_instance)
