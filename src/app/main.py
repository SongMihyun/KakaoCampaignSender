# FILE: src/app/main.py
from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

from app.startup_args import parse_startup_args

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
    """
    COM STA 선점(가능하면 True).
    - S_OK / S_FALSE: 초기화 성공
    - RPC_E_CHANGED_MODE: 이미 MTA 등 다른 모드로 초기화되어 모드 변경 불가 (이 경우 False)
    """
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
    startup_args = parse_startup_args(sys.argv[1:])

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    splash = None

    def _ensure_splash():
        nonlocal splash
        if splash is not None:
            return splash
        try:
            from frontend.app.splash import make_splash

            splash = make_splash()
            splash.show()
            app.processEvents()
            return splash
        except Exception:
            splash = None
            return None

    def _splash_msg(msg: str) -> None:
        _ensure_splash()
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

    # 예약발송으로 자동 기동된 경우에는 업데이트/로그인 때문에 예약발송이 막히지 않도록 스킵
    if not startup_args.is_scheduled_launch:
        try:
            from app.version import __version__, LATEST_JSON_URL
            from frontend.app.splash import run_startup_update_if_needed

            update_result = run_startup_update_if_needed(LATEST_JSON_URL, __version__)
            logging.getLogger("main").info(
                "startup update check result: started=%s reason=%s latest=%s",
                update_result.started,
                update_result.reason,
                update_result.latest_version,
            )
            if update_result.started:
                if com_inited:
                    try:
                        ole32.CoUninitialize()
                    except Exception:
                        pass
                sys.exit(0)
        except Exception as e:
            logging.getLogger("main").exception(f"startup update failed: {e}")

        # 로그인 창이 스플래시에 가려지지 않도록 로그인은 스플래시 생성 전에 수행
        try:
            from frontend.dialogs.login_dialog import LoginDialog

            ok = LoginDialog.run_login()
            if not ok:
                sys.exit(0)
        except Exception as e:
            logging.getLogger("main").exception(f"login init failed: {e}")
            sys.exit(0)

    _splash_msg("데이터베이스 초기화 중…")
    try:
        from backend.database.db_bootstrap import ensure_db_initialized

        ensure_db_initialized()
    except Exception as e:
        logging.getLogger("main").exception(f"DB init failed: {e}")

    _splash_msg("UI 로딩 중…")
    from frontend.app.main_window import MainWindow

    win = MainWindow(startup_args=startup_args)
    if startup_args.minimized:
        win.showMinimized()
    else:
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
