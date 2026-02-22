# src/app/update/update_service.py
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QApplication

from app.update.updater import Updater
from app.update.update_dialog import UpdateDialog
from app.update.update_config import UPDATE_CONFIG


def check_and_run_update(parent=None) -> bool:
    """
    return True if update started and app should exit
    """
    updater = Updater(UPDATE_CONFIG.latest_json_url, timeout_sec=4.0)
    m = updater.fetch_latest_manifest()
    if not m:
        return False

    if not updater.needs_update(m):
        return False

    # 정책: 자동업데이트(무인)로 갈지, 사용자 확인 받을지 선택
    # 우선은 확인 받는 형태
    ret = QMessageBox.question(
        parent,
        "업데이트",
        f"새 버전({m.version})이 있습니다.\n지금 업데이트하시겠습니까?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if ret != QMessageBox.StandardButton.Yes:
        return False

    dlg = UpdateDialog(parent, updater=updater, manifest=m)
    ok = dlg.start()
    if not ok:
        return False

    # 다운로드+검증 완료 → 설치 실행 → 앱 종료
    updater.run_silent_install(dlg._installer_path)  # 내부 필드 접근 싫으면 getter로 바꿔도 됨

    # 설치 진행 중 충돌 방지: 즉시 종료 권장
    QApplication.quit()
    return True