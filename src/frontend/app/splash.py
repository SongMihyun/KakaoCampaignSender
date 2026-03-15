# FILE: src/frontend/app/splash.py
from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QSplashScreen

from backend.updates.updater import Updater, is_newer


@dataclass(frozen=True)
class StartupUpdateResult:
    started: bool
    latest_version: str = ""
    installer_path: str = ""
    reason: str = ""


def make_splash() -> QSplashScreen:
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


def run_startup_update_if_needed(
    latest_json_url: str,
    current_version: str,
    *,
    timeout_sec: float = 5.0,
) -> StartupUpdateResult:
    """
    앱 시작 시점에서 최신 버전을 확인하고, 새 버전이 있으면
    설치 파일을 다운로드한 뒤 silent install을 즉시 실행한다.

    주의:
    - PyInstaller EXE(= frozen) 환경에서만 동작시킨다.
    - 개발 소스 실행 시에는 자동 업데이트를 건너뛴다.
    """
    if not getattr(sys, "frozen", False):
        return StartupUpdateResult(False, reason="not_frozen")

    updater = Updater(latest_json_url, timeout_sec=timeout_sec)
    manifest = updater.fetch_latest_manifest()
    if not manifest:
        return StartupUpdateResult(False, reason="manifest_unavailable")

    if not manifest.version or not manifest.url:
        return StartupUpdateResult(False, reason="manifest_invalid")

    if not is_newer(manifest.version, current_version):
        return StartupUpdateResult(False, latest_version=manifest.version, reason="up_to_date")

    installer_path = updater.download_installer(manifest.url)
    if not updater.verify_sha256(installer_path, manifest.sha256):
        return StartupUpdateResult(False, latest_version=manifest.version, reason="sha256_mismatch")

    updater.run_silent_install(
        installer_path,
        close_applications=True,
        restart_applications=True,
    )
    return StartupUpdateResult(
        True,
        latest_version=manifest.version,
        installer_path=installer_path,
        reason="installer_started",
    )
