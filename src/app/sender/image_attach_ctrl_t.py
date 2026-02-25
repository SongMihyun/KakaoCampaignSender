# ✅ FILE: src/app/sender/image_attach_ctrl_t.py

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Mapping, Optional

from app.sender.image_attach_cache import get_or_create_temp_png


def send_png_via_ctrl_t(
    *,
    png_bytes: bytes,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    ensure_foreground_chat: Callable[[], None],
    focus_chat_input_best_effort: Callable[[], bool],
    sleep_abs: Callable[[float], None],
    send_image_dialog_hook: Callable[..., bool],
    timeout_sec: float,
    key_delay: float,
    debug: bool,
    log: Callable[[str], None],
    prefix: str = "kakao_sender_attach",
    ttl_sec: float = 60 * 60 * 6,
    cache_dir: Optional[Path] = None,
    timings: Optional[Mapping[str, float]] = None,
    dlg_timings: Optional[Mapping[str, float]] = None,

    # ✅ 추가(있으면 넣고, 없으면 None으로 호출해도 됨)
    prefer_hwnd: int = 0,
    get_foreground_hwnd: Optional[Callable[[], int]] = None,
) -> bool:
    if not png_bytes:
        return True

    tm = dict(timings or {})

    def _t(key: str, default: float = 0.0) -> float:
        return float(tm.get(key, default))

    def _ms(dt: float) -> int:
        return int(dt * 1000)

    # 0) 캐시(파일 준비)
    t_cache0 = time.perf_counter()
    try:
        tmp_path = get_or_create_temp_png(
            png_bytes=png_bytes,
            prefix=prefix,
            ttl_sec=ttl_sec,
            cache_dir=cache_dir,
        )
    except Exception as e:
        log(f"[CTRL+T] temp cache get/create failed: {e}")
        return False
    log(f"[CTRL+T] cache:end ms={_ms(time.perf_counter() - t_cache0)} path={tmp_path} size={len(png_bytes)}")

    t_focus0 = time.perf_counter()

    # 2) Ctrl+T
    t_k0 = time.perf_counter()
    try:
        log(f"[CTRL+T] key_ctrl_t:begin prefer_hwnd={prefer_hwnd}")
        send_keys_fast("^t")
        sleep_abs(_t("after_ctrl_t"))
        log(f"[CTRL+T] key_ctrl_t:end ms={_ms(time.perf_counter() - t_k0)}")
    except Exception as e:
        log(f"[CTRL+T] key_ctrl_t failed: {e}")
        return False

    # 3) 경로 클립보드
    t_cb0 = time.perf_counter()
    try:
        log(f"[CTRL+T] set_clipboard_path:begin prefer_hwnd={prefer_hwnd}")
        set_clipboard_text(str(tmp_path))
        sleep_abs(_t("clipboard_settle"))
        log(f"[CTRL+T] set_clipboard_path:end ms={_ms(time.perf_counter() - t_cb0)}")
    except Exception as e:
        log(f"[CTRL+T] set_clipboard_path failed: {e}")
        return False

    # 4) 붙여넣기 + Enter
    t_p0 = time.perf_counter()
    try:
        log(f"[CTRL+T] paste_path:begin prefer_hwnd={prefer_hwnd}")
        send_keys_fast("^v")
        sleep_abs(_t("after_paste_path"))
        log(f"[CTRL+T] paste_path:end ms={_ms(time.perf_counter() - t_p0)}")

        t_e0 = time.perf_counter()
        log(f"[CTRL+T] enter_path:begin prefer_hwnd={prefer_hwnd}")
        send_keys_fast("{ENTER}")
        sleep_abs(_t("after_enter_path"))
        log(f"[CTRL+T] enter_path:end ms={_ms(time.perf_counter() - t_e0)}")
    except Exception as e:
        log(f"[CTRL+T] paste/enter flow failed: {e}")
        return False

    # 5) 전송 다이얼로그 훅
    t_d0 = time.perf_counter()
    try:
        ok = bool(
            send_image_dialog_hook(
                timeout_sec=timeout_sec,
                key_delay=key_delay,
                debug=debug,
                log=log,
                timings=dlg_timings,
                prefer_hwnd=int(prefer_hwnd or 0),
            )
        )
        log(f"[CTRL+T] dialog_hook:end ok={ok} ms={_ms(time.perf_counter() - t_d0)} prefer_hwnd={prefer_hwnd}")
        log(f"[CTRL+T] send result={ok} path={tmp_path}")
        return ok
    except Exception as e:
        log(f"[CTRL+T] dialog hook failed: {e}")
        return False