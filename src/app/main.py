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

    # 로그인 화면이 스플래시에 가려지지 않도록 먼저 로그인 후 스플래시를 띄운다.
    try:
        from frontend.dialogs.login_dialog import LoginDialog

        ok = LoginDialog.run_login()
        if not ok:
            sys.exit(0)
    except Exception:
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

    _splash_msg("업데이트 확인 중…")
    try:
        from app.version import __version__, LATEST_JSON_URL
        from frontend.app.splash import check_and_prepare_update, set_pending_update

        plan = check_and_prepare_update(LATEST_JSON_URL, __version__)
        if plan.available:
            set_pending_update(plan)
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

    win = MainWindow()
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
