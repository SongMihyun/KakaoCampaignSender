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

# ✅ wintypes.HRESULT 보강 (환경에 따라 미정의)
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
    # ✅ stdout 로깅 강제
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # ✅ 개발 중 TRACE 기본 ON
    os.environ.setdefault("KAKAO_TRACE", "1")

    # ✅ 0) COM STA 선점 (가장 먼저!)
    com_inited = _com_init_sta_main_best_effort()

    # ✅ 1) QApplication을 최대한 빨리 올려서 "실행 중 표시"를 즉시 제공
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # ✅ 2) 스플래시(로딩 표시) 즉시 노출
    splash = None
    try:
        from app.ui.splash import make_splash

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

    # ✅ 3) 업데이트 체크/다운로드 준비 (실패해도 앱은 계속 실행)
    _splash_msg("업데이트 확인 중…")
    try:
        from app.version import __version__, LATEST_JSON_URL
        from app.updater import check_and_prepare_update, set_pending_update

        plan = check_and_prepare_update(LATEST_JSON_URL, __version__)
        if plan.available:
            # ✅ 종료 시 설치되도록 예약만 걸어둠
            set_pending_update(plan)
    except Exception:
        # 업데이트 실패는 런타임 중단 사유 아님
        pass

    # ✅ 4) DB 초기화
    _splash_msg("데이터베이스 초기화 중…")
    try:
        from app.data.db_bootstrap import ensure_db_initialized

        ensure_db_initialized()
    except Exception as e:
        logging.getLogger("main").exception(f"DB init failed: {e}")

    # ✅ 5) UI 로딩 (무거운 import는 여기서)
    _splash_msg("UI 로딩 중…")
    from ui.main_window import MainWindow  # 현재 사용 중 경로 그대로

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