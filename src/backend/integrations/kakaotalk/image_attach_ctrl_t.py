from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Any

from backend.integrations.kakaotalk.image_attach_cache import get_or_create_temp_png
from backend.integrations.windows.win32_core import (
    close_open_dialog_if_any,
    ensure_foreground_chat_hwnd,
    lazy_pywinauto,
)

def _safe_cleanup_after_file_dialog(
    *,
    prefer_hwnd: int,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> None:
    """
    파일 열기 / 파일 전송 관련 창이 남았을 때 최대한 정리하고
    다시 채팅창으로 복귀시킨다.
    """
    try:
        close_open_dialog_if_any()
        sleep_abs(0.05)
    except Exception as e:
        log(f"[FILE_DIALOG][CLEANUP] close_open_dialog_if_any fail: {e}")

    try:
        if int(prefer_hwnd or 0) > 0:
            ensure_foreground_chat_hwnd(int(prefer_hwnd))
            sleep_abs(0.08)
    except Exception as e:
        log(f"[FILE_DIALOG][CLEANUP] ensure_foreground_chat_hwnd fail: {e}")
def _build_names_text(paths: Sequence[str]) -> str:
    """
    파일 이름 칸에 넣을 텍스트.
    반드시 파일명만, 그리고 각 파일명을 quote 해서 넣는다.

    예:
      "img001.jpg" "img002.jpg" "img003.png"
    """
    names: list[str] = []
    for p in paths or []:
        name = os.path.basename(str(p or "").strip())
        if not name:
            continue
        name = name.replace('"', "")
        names.append(f'"{name}"')
    return " ".join(names)


def _safe_window_text(el) -> str:
    try:
        return str(el.window_text() or "").strip()
    except Exception:
        return ""


def _safe_rect_area(el) -> int:
    try:
        r = el.rectangle()
        w = max(0, int(r.width()))
        h = max(0, int(r.height()))
        return w * h
    except Exception:
        return 0


def _iter_button_like_descendants(root) -> list[Any]:
    """
    UIA 기준으로 버튼/분할버튼/하이퍼링크/커스텀 버튼성 요소를 넓게 수집.
    """
    out: list[Any] = []

    control_types = [
        "Button",
        "SplitButton",
        "Hyperlink",
        "MenuItem",
        "Custom",
    ]

    for ct in control_types:
        try:
            items = root.descendants(control_type=ct)
        except Exception:
            items = []
        out.extend(items)

    return out


def _click_uia_element(
    el,
    *,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> bool:
    """
    UIA 요소 클릭:
    1) invoke
    2) click_input
    3) select
    4) set_focus + SPACE
    """
    txt = _safe_window_text(el)

    try:
        try:
            log(f"[FILE_SEND][CLICK_TRY] method=invoke text={txt!r}")
            el.invoke()
            sleep_abs(0.20)
            log(f"[FILE_SEND][CLICK_OK] method=invoke text={txt!r}")
            return True
        except Exception as e:
            log(f"[FILE_SEND][CLICK_FAIL] method=invoke text={txt!r} err={e}")

        try:
            log(f"[FILE_SEND][CLICK_TRY] method=click_input text={txt!r}")
            el.click_input()
            sleep_abs(0.20)
            log(f"[FILE_SEND][CLICK_OK] method=click_input text={txt!r}")
            return True
        except Exception as e:
            log(f"[FILE_SEND][CLICK_FAIL] method=click_input text={txt!r} err={e}")

        try:
            log(f"[FILE_SEND][CLICK_TRY] method=select text={txt!r}")
            el.select()
            sleep_abs(0.20)
            log(f"[FILE_SEND][CLICK_OK] method=select text={txt!r}")
            return True
        except Exception as e:
            log(f"[FILE_SEND][CLICK_FAIL] method=select text={txt!r} err={e}")

        try:
            log(f"[FILE_SEND][CLICK_TRY] method=set_focus_space text={txt!r}")
            el.set_focus()
            sleep_abs(0.10)
            type_keys = getattr(el, "type_keys", None)
            if callable(type_keys):
                type_keys(" ")
                sleep_abs(0.20)
                log(f"[FILE_SEND][CLICK_OK] method=set_focus_space text={txt!r}")
                return True
            log(f"[FILE_SEND][CLICK_FAIL] method=set_focus_space text={txt!r} err=no_type_keys")
        except Exception as e:
            log(f"[FILE_SEND][CLICK_FAIL] method=set_focus_space text={txt!r} err={e}")

    except Exception as e:
        log(f"[FILE_SEND][ELEMENT_CLICK_EXCEPTION] text={txt!r} err={e}")

    return False

def _find_send_button_in_chat_surface(
    *,
    chat_hwnd: int,
    log: Callable[[str], None],
):
    """
    카카오 채팅창(UIA 트리) 안에서
    - '4개 전송'
    - '전송'
    버튼을 직접 찾는다.
    """
    try:
        Desktop, _, _ = lazy_pywinauto()
        root = Desktop(backend="uia").window(handle=int(chat_hwnd))
    except Exception as e:
        log(f"[FILE_SEND][ROOT_ATTACH_FAIL] hwnd={chat_hwnd} err={e}")
        return None

    try:
        root_text = _safe_window_text(root)
    except Exception:
        root_text = ""



    candidates = _iter_button_like_descendants(root)


    preferred: list[Any] = []
    fallback: list[Any] = []

    # 너무 많을 수 있으니 앞 40개만 상세 로그
    max_debug = 40
    debug_idx = 0

    for el in candidates:
        try:
            txt = _safe_window_text(el)
            area = _safe_rect_area(el)

            if debug_idx < max_debug:
                try:
                    ctrl_type = getattr(getattr(el, "element_info", None), "control_type", "")
                except Exception:
                    ctrl_type = ""
                log(f"[FILE_SEND][CANDIDATE] idx={debug_idx} text={txt!r} area={area} type={ctrl_type!r}")
                debug_idx += 1

            if not txt:
                continue

            if re.search(r"\d+\s*개\s*전송", txt):
                preferred.append((area, el))
                continue

            if txt == "전송":
                preferred.append((area, el))
                continue

            if "전송" in txt:
                fallback.append((area, el))
                continue
        except Exception as e:
            log(f"[FILE_SEND][CANDIDATE_ERR] err={e}")
            continue



    if preferred:
        preferred.sort(key=lambda x: x[0], reverse=True)
        btn = preferred[0][1]
        try:
            log(f"[FILE_SEND][MATCH_PICK] preferred text={_safe_window_text(btn)!r}")
        except Exception:
            pass
        return btn

    if fallback:
        fallback.sort(key=lambda x: x[0], reverse=True)
        btn = fallback[0][1]
        try:
            log(f"[FILE_SEND][MATCH_PICK] fallback text={_safe_window_text(btn)!r}")
        except Exception:
            pass
        return btn

    return None


def send_files_dialog_hook(
    *,
    chat_hwnd: int,
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    timeout_sec: float = 2.5,
) -> bool:
    """
    현재 환경 전용 최적화:
    파일 전송 UI는 UIA 탐색보다 TAB->TAB->ENTER가 더 빠르고 안정적이다.
    실패/잔류창 상황까지 고려해 정리 로직 포함.
    """
    try:
        log(f"[FILE_SEND][DIRECT_BEGIN] hwnd={chat_hwnd}")

        send_keys_fast("{TAB}")
        sleep_abs(0.05)

        send_keys_fast("{TAB}")
        sleep_abs(0.05)

        send_keys_fast("{ENTER}")
        sleep_abs(0.18)

        _safe_cleanup_after_file_dialog(
            prefer_hwnd=int(chat_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
        )

        log("[FILE_SEND][DIRECT_OK] TAB->TAB->ENTER")
        return True

    except Exception as e:
        log(f"[FILE_SEND][DIRECT_FAIL] err={e}")

        _safe_cleanup_after_file_dialog(
            prefer_hwnd=int(chat_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
        )
        return False

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
    prefer_hwnd: int = 0,
    get_foreground_hwnd: Optional[Callable[[], int]] = None,
) -> bool:
    """
    단일 파일 Ctrl+T.
    기존 검증된 흐름 유지.
    """
    if not png_bytes:
        return True

    tm = dict(timings or {})

    def _t(key: str, default: float = 0.0) -> float:
        return float(tm.get(key, default))

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

    try:
        ensure_foreground_chat()
        focus_chat_input_best_effort()
        sleep_abs(0.02)
    except Exception:
        pass

    try:
        send_keys_fast("^t")
        sleep_abs(_t("after_ctrl_t"))
    except Exception as e:
        log(f"[CTRL+T] key_ctrl_t failed: {e}")
        return False

    try:
        set_clipboard_text(str(tmp_path))
        sleep_abs(_t("clipboard_settle"))
    except Exception as e:
        log(f"[CTRL+T] set_clipboard_path failed: {e}")
        return False

    try:
        send_keys_fast("^v")
        sleep_abs(_t("after_paste_path"))
        send_keys_fast("{ENTER}")
        sleep_abs(_t("after_enter_path"))
    except Exception as e:
        log(f"[CTRL+T] paste/enter flow failed: {e}")
        return False

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

        if not ok:
            try:
                close_open_dialog_if_any()
            except Exception:
                pass
            try:
                ensure_foreground_chat_hwnd(int(prefer_hwnd or 0))
            except Exception:
                pass

        return bool(ok)
    except Exception as e:
        log(f"[CTRL+T] dialog hook failed: {e}")
        return False


def send_files_via_ctrl_t(
    *,
    file_paths: Sequence[str],
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    ensure_foreground_chat: Callable[[], None],
    focus_chat_input_best_effort: Callable[[], bool],
    sleep_abs: Callable[[float], None],
    timeout_sec: float,
    key_delay: float,
    debug: bool,
    log: Callable[[str], None],
    timings: Optional[Mapping[str, float]] = None,
    prefer_hwnd: int = 0,
    get_foreground_hwnd: Optional[Callable[[], int]] = None,
) -> bool:
    valid_paths = [str(p).strip() for p in (file_paths or []) if str(p).strip()]
    if not valid_paths:
        return True

    for p in valid_paths:
        if not os.path.exists(p):
            log(f"[CTRL+T-MULTI] file not found: {p}")
            return False

    tm = dict(timings or {})

    def _t(key: str, default: float = 0.0) -> float:
        return float(tm.get(key, default))

    bundle_dir = os.path.dirname(valid_paths[0])
    if not bundle_dir:
        log("[CTRL+T-MULTI] invalid bundle_dir")
        return False

    for p in valid_paths:
        if os.path.dirname(p) != bundle_dir:
            log(f"[CTRL+T-MULTI] different dirs detected: {p}")
            return False

    names_text = _build_names_text(valid_paths)
    if not names_text:
        return False

    log(f"[CTRL+T-MULTI] bundle_dir={bundle_dir}")
    log(f"[CTRL+T-MULTI] names_text={names_text}")

    try:
        ensure_foreground_chat()
        focus_chat_input_best_effort()
        sleep_abs(0.02)
    except Exception as e:
        log(f"[CTRL+T-MULTI] pre-focus fail: {e}")

    try:
        # 1) 열기 창
        send_keys_fast("^t")
        sleep_abs(_t("after_ctrl_t", 0.20))

        # 2) 주소창 이동
        send_keys_fast("%d")
        sleep_abs(0.10)

        set_clipboard_text(bundle_dir)
        sleep_abs(_t("clipboard_settle", 0.03))
        send_keys_fast("^v")
        sleep_abs(0.08)
        send_keys_fast("{ENTER}")
        sleep_abs(0.35)

        # 3) 파일 이름 칸
        send_keys_fast("%n")
        sleep_abs(0.10)

        # 4) 파일명만 입력
        set_clipboard_text(names_text)
        sleep_abs(_t("clipboard_settle", 0.03))
        send_keys_fast("^v")
        sleep_abs(_t("after_paste_path", 0.08))

        # 5) 선택 확정
        send_keys_fast("{ENTER}")
        sleep_abs(_t("after_enter_path", 0.25))

        # 6) 파일 전송 확인
        ok = send_files_dialog_hook(
            chat_hwnd=int(prefer_hwnd or 0),
            send_keys_fast=send_keys_fast,
            sleep_abs=sleep_abs,
            log=log,
            timeout_sec=max(2.0, float(timeout_sec)),
        )
        if not ok:
            _safe_cleanup_after_file_dialog(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
            )
            return False

        # 최종 정리
        _safe_cleanup_after_file_dialog(
            prefer_hwnd=int(prefer_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
        )
        sleep_abs(0.12)
        return True

    except Exception as e:
        log(f"[CTRL+T-MULTI] exception: {e}")

        _safe_cleanup_after_file_dialog(
            prefer_hwnd=int(prefer_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
        )
        return False