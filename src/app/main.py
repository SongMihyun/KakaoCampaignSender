# FILE: src/app/main.py
from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

# ----------------------------
# COM STA init (main thread) - must run BEFORE heavy imports
# ----------------------------
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

COINIT_APARTMENTTHREADED = 0x2

S_OK = 0x00000000
S_FALSE = 0x00000001
RPC_E_CHANGED_MODE = 0x80010106

HRESULT = getattr(wintypes, "HRESULT", ctypes.c_long)

ole32.CoInitializeEx.argtypes = [wintypes.LPVOID, wintypes.DWORD]
ole32.CoInitializeEx.restype = HRESULT
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None


def _com_init_sta_main_best_effort() -> bool:
    hr = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
    if hr in (S_OK, S_FALSE):
        return True
    if hr == RPC_E_CHANGED_MODE:
        return False
    return False


def _prepare_update_with_ui(app, splash_msg) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QProgressDialog

    from app.relaunch import relaunch_executable_and_args
    from app.version import __version__, LATEST_JSON_URL
    from backend.updates.updater import UpdatePlan, Updater, is_newer, set_pending_update

    current_version = (__version__ or "").strip()
    is_release_build = bool(getattr(sys, "frozen", False)) and current_version and current_version != "__VERSION__"
    if not is_release_build:
        return

    splash_msg("업데이트 확인 중...")

    updater = Updater(LATEST_JSON_URL, timeout_sec=7.0)
    manifest = updater.fetch_latest_manifest()
    if not manifest or not manifest.version or not manifest.url:
        return
    if not is_newer(manifest.version, current_version):
        return

    progress = QProgressDialog("새 버전 설치 파일 다운로드 중...", "", 0, 100)
    progress.setWindowTitle("업데이트 다운로드")
    progress.setWindowModality(Qt.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setCancelButton(None)
    progress.setValue(0)

    def on_progress(downloaded: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, int(downloaded * 100 / total)))
            progress.setMaximum(100)
            progress.setValue(percent)
            progress.setLabelText(
                f"업데이트 {manifest.version} 다운로드 중...\n"
                f"{downloaded / (1024 * 1024):.1f}MB / {total / (1024 * 1024):.1f}MB"
            )
        else:
            progress.setMaximum(0)
            progress.setLabelText(f"업데이트 {manifest.version} 다운로드 중...")
        app.processEvents()

    try:
        installer_path = updater.download_installer(
            manifest.url,
            on_progress=on_progress,
        )
        progress.setValue(100)
    except Exception as e:
        progress.close()
        QMessageBox.warning(None, "업데이트 실패", f"업데이트 다운로드에 실패했습니다.\n{e}")
        return
    finally:
        progress.close()

    if not updater.verify_sha256(installer_path, manifest.sha256):
        QMessageBox.warning(None, "업데이트 실패", "설치 파일 검증에 실패했습니다. 다음 실행 때 다시 시도합니다.")
        return

    relaunch_exe, relaunch_args, relaunch_cwd = relaunch_executable_and_args()
    set_pending_update(
        UpdatePlan(
            True,
            latest=manifest,
            installer_path=installer_path,
            relaunch_executable=relaunch_exe,
            relaunch_args=tuple(relaunch_args),
            relaunch_working_dir=relaunch_cwd,
            reason="prepared",
        )
    )

    QMessageBox.information(
        None,
        "업데이트 준비 완료",
        f"버전 {manifest.version} 설치 파일을 다운로드했습니다.\n\n"
        "앱을 종료하면 자동으로 설치가 진행되고, 설치가 끝나면 카센더를 다시 실행합니다.",
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    os.environ.setdefault("KAKAO_TRACE", "1")
    com_inited = _com_init_sta_main_best_effort()

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    update_checked_before_auth = False

    try:
        _prepare_update_with_ui(app, lambda _msg: None)
        update_checked_before_auth = True
    except Exception:
        pass

    # 로그인 화면이 스플래시에 가려지지 않도록 먼저 로그인 후 스플래시를 띄운다.
    try:
        from backend.domains.auth import AuthService
        from frontend.dialogs.login_dialog import LoginDialog

        auth_service = AuthService()
        session = auth_service.current_session()
        if session is None:
            session = LoginDialog.run_login(auth_service=auth_service)
        if session is None:
            sys.exit(0)
        from app.paths import set_active_user_uuid
        from app.version import __version__
        from backend.database.legacy_orphan_backup import backup_legacy_db_if_needed

        active_user_id = session.user_uuid or session.provider_user_id
        set_active_user_uuid(active_user_id)
        backup_legacy_db_if_needed(app_version=str(__version__ or ""))
        if not auth_service.should_persist_session():
            app.aboutToQuit.connect(auth_service.clear_session)
    except Exception:
        logging.getLogger("main").exception("Authentication failed")
        sys.exit(0)

    splash = None
    try:
        from frontend.app.splash import make_splash

        splash = make_splash()
        splash.show()
        app.processEvents()
    except Exception:
        splash = None

    def _splash_msg(msg: str) -> None:
        if splash is None:
            return
        try:
            splash.showMessage(
                msg,
                splash.messageAlignment(),
                splash.messageColor(),
            )
            app.processEvents()
        except Exception:
            pass

    try:
        if splash is not None:
            splash.hide()
        if not update_checked_before_auth:
            _prepare_update_with_ui(app, _splash_msg)
    except Exception:
        pass
    finally:
        if splash is not None:
            try:
                splash.show()
                app.processEvents()
            except Exception:
                pass

    _splash_msg("데이터베이스 초기화 중…")
    try:
        from backend.database.db_bootstrap import ensure_db_initialized

        ensure_db_initialized()
    except Exception as e:
        logging.getLogger("main").exception(f"DB init failed: {e}")

    _splash_msg("UI 로딩 중…")
    from frontend.app.main_window import MainWindow

    win = MainWindow(session=session)
    win.show()

    if splash is not None:
        try:
            splash.finish(win)
        except Exception:
            pass

    code = app.exec()

    if com_inited:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass

    sys.exit(code)


if __name__ == "__main__":
    main()
