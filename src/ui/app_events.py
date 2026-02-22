# src/ui/app_events.py
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppEvents(QObject):
    """
    앱 전역 이벤트 버스
    - contacts_changed: 대상자(contacts) 테이블이 변경될 때
    - groups_changed: 그룹(groups/mapping) 변경될 때(확장용)
    """
    contacts_changed = Signal()
    groups_changed = Signal()


# 전역 싱글톤
app_events = AppEvents()
