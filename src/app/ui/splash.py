# src/app/ui/splash.py
from __future__ import annotations

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QSplashScreen
from PySide6.QtCore import Qt


def make_splash() -> QSplashScreen:
    # 이미지 없으면 빈 픽셀맵으로도 가능
    pm = QPixmap(520, 220)
    pm.fill(Qt.GlobalColor.white)

    splash = QSplashScreen(pm)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.showMessage(
        "KakaoSender 시작 중…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        Qt.GlobalColor.black,
    )
    return splash