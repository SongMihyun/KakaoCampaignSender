# path: src/backend/integrations/kakaotalk/image_attach_ctrl_t.py
from __future__ import annotations

import ctypes
import os
import re
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from backend.integrations.kakaotalk.image_attach_cache import get_or_create_temp_png
from backend.integrations.windows.win32_core import (
    GA_ROOT,
    close_open_dialog_if_any,
    ensure_foreground_chat_hwnd,
    get_class_name,
    get_foreground_hwnd,
    get_window_rect,
    get_window_text,
    lazy_pywinauto,
    user32,
)

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
WM_COMMAND = 0x0111
EM_SETSEL = 0x00B1
IDOK = 1
EDT1 = 0x0480

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumWindowsProc, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL
user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
user32.GetDlgCtrlID.restype = ctypes.c_int


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


def _build_absolute_paths_text(paths: Sequence[str]) -> str:
    out: list[str] = []
    for p in paths or []:
        ap = os.path.abspath(str(p or "").strip())
        if not ap:
            continue
        ap = ap.replace('"', "")
        out.append(f'"{ap}"')
    return " ".join(out)


def _normalize_compare_text(text: str) -> str:
    s = str(text or "").strip().strip('"')
    s = s.replace("/", "\\")
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


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

    candidates = _iter_button_like_descendants(root)

    preferred: list[Any] = []
    fallback: list[Any] = []

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


def _root_hwnd(hwnd: int) -> int:
    try:
        h = int(hwnd or 0)
        if h <= 0:
            return 0
        r = int(user32.GetAncestor(wintypes.HWND(h), GA_ROOT) or 0)
        return r if r > 0 else h
    except Exception:
        return int(hwnd or 0)


def _iter_top_windows() -> list[int]:
    out: list[int] = []

    @EnumWindowsProc
    def _cb(hwnd, lparam):
        try:
            h = int(hwnd or 0)
            if h > 0 and bool(user32.IsWindowVisible(wintypes.HWND(h))):
                out.append(h)
        except Exception:
            pass
        return True

    user32.EnumWindows(_cb, 0)
    return out


def _iter_child_windows(parent_hwnd: int, *, recursive: bool = True) -> list[int]:
    out: list[int] = []

    def _walk(hwnd_parent: int) -> None:
        @EnumWindowsProc
        def _cb(hwnd, lparam):
            try:
                h = int(hwnd or 0)
                if h > 0:
                    out.append(h)
                    if recursive:
                        _walk(h)
            except Exception:
                pass
            return True

        user32.EnumChildWindows(wintypes.HWND(int(hwnd_parent)), _cb, 0)

    if int(parent_hwnd or 0) > 0:
        _walk(int(parent_hwnd))
    return out


def _looks_like_open_dialog(hwnd: int) -> bool:
    h = int(hwnd or 0)
    if h <= 0:
        return False
    cls = str(get_class_name(h) or "")
    if cls != "#32770":
        return False
    title = str(get_window_text(h) or "").strip()
    if not title:
        return True
    return ("열기" in title) or ("open" in title.casefold())


def _wait_for_open_dialog(
    *,
    timeout_sec: float,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    get_foreground_hwnd_cb: Optional[Callable[[], int]] = None,
) -> int:
    deadline = time.perf_counter() + max(0.8, float(timeout_sec))
    last_fg_root = 0
    while time.perf_counter() < deadline:
        fg = int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0)
        fg_root = _root_hwnd(fg)
        last_fg_root = fg_root
        if _looks_like_open_dialog(fg_root):
            log(f"[CTRL+T-MULTI] open dialog found by fg root={fg_root}")
            return fg_root

        for h in _iter_top_windows():
            if _looks_like_open_dialog(h):
                log(f"[CTRL+T-MULTI] open dialog found by enum hwnd={h}")
                return h
        sleep_abs(0.05)

    log(f"[CTRL+T-MULTI] open dialog not found fg_root={last_fg_root}")
    return 0


def _get_edit_text_via_messages(hwnd: int) -> str:
    h = int(hwnd or 0)
    if h <= 0:
        return ""
    try:
        length = int(user32.SendMessageW(wintypes.HWND(h), WM_GETTEXTLENGTH, 0, 0) or 0)
        buf = ctypes.create_unicode_buffer(max(1, length + 2))
        user32.SendMessageW(wintypes.HWND(h), WM_GETTEXT, len(buf), ctypes.cast(buf, ctypes.c_void_p).value or 0)
        return str(buf.value or "")
    except Exception:
        return ""


def _find_filename_edit_hwnd(dialog_hwnd: int, *, log: Callable[[str], None]) -> int:
    candidates: list[tuple[int, int]] = []
    for h in _iter_child_windows(dialog_hwnd, recursive=True):
        try:
            if str(get_class_name(h) or "") != "Edit":
                continue
            l, t, r, b = get_window_rect(h)
            if r <= l or b <= t:
                continue
            area = max(0, r - l) * max(0, b - t)
            ctrl_id = int(user32.GetDlgCtrlID(wintypes.HWND(h)) or 0)
            parent = int(user32.GetParent(wintypes.HWND(h)) or 0)
            parent_id = int(user32.GetDlgCtrlID(wintypes.HWND(parent)) or 0) if parent > 0 else 0
            parent_cls = str(get_class_name(parent) or "") if parent > 0 else ""
            score = (b * 10) + area
            if ctrl_id == EDT1:
                score += 10000000
            if parent_id == EDT1:
                score += 5000000
            if parent_cls in {"ComboBox", "ComboBoxEx32"}:
                score += 1000000
            candidates.append((score, h))
            log(f"[CTRL+T-MULTI] edit candidate hwnd={h} ctrl_id={ctrl_id} parent={parent} parent_id={parent_id} parent_cls={parent_cls!r} rect={(l,t,r,b)}")
        except Exception:
            continue

    if not candidates:
        log("[CTRL+T-MULTI] filename edit not found")
        return 0

    candidates.sort(reverse=True)
    hwnd = int(candidates[0][1])
    log(f"[CTRL+T-MULTI] filename edit hwnd={hwnd}")
    return hwnd


def _set_edit_text_verified(
    edit_hwnd: int,
    text: str,
    *,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    timeout_sec: float = 1.2,
) -> bool:
    h = int(edit_hwnd or 0)
    if h <= 0:
        return False

    # ctypes wrapper 환경에서는 LPARAM에 c_wchar_p를 직접 넘기면
    # 'object cannot be interpreted as an integer' 예외가 날 수 있다.
    # 반드시 버퍼 포인터 값을 정수 LPARAM으로 넘긴다.
    try:
        buf = ctypes.create_unicode_buffer(str(text or ""))
        lp = ctypes.cast(buf, ctypes.c_void_p).value or 0
        user32.SendMessageW(wintypes.HWND(h), WM_SETTEXT, 0, lp)
    except Exception as e:
        log(f"[CTRL+T-MULTI] WM_SETTEXT fail hwnd={h} err={e}")
        return False

    deadline = time.perf_counter() + max(0.6, float(timeout_sec))
    target = _normalize_compare_text(text)
    last_actual = ""
    while time.perf_counter() < deadline:
        last_actual = _get_edit_text_via_messages(h)
        current = _normalize_compare_text(last_actual)
        if current == target:
            log(f"[CTRL+T-MULTI] filename text verified hwnd={h}")
            return True
        sleep_abs(0.05)

    try:
        user32.SetForegroundWindow(wintypes.HWND(h))
    except Exception:
        pass
    try:
        user32.SendMessageW(wintypes.HWND(h), EM_SETSEL, 0, -1)
    except Exception:
        pass

    deadline = time.perf_counter() + max(0.8, float(timeout_sec))
    while time.perf_counter() < deadline:
        last_actual = _get_edit_text_via_messages(h)
        current = _normalize_compare_text(last_actual)
        if current == target:
            log(f"[CTRL+T-MULTI] filename text verified hwnd={h} (retry)")
            return True
        sleep_abs(0.05)

    log(
        "[CTRL+T-MULTI] filename verify fail "
        f"expected={text!r} actual={last_actual!r}"
    )
    return False


def _find_open_button_hwnd(dialog_hwnd: int, *, log: Callable[[str], None]) -> int:
    fallback_idok = 0
    fallback_area = 0
    for h in _iter_child_windows(dialog_hwnd, recursive=True):
        try:
            if str(get_class_name(h) or "") != "Button":
                continue
            txt = str(get_window_text(h) or "").strip()
            ctrl_id = int(user32.GetDlgCtrlID(wintypes.HWND(h)) or 0)
            l, t, r, b = get_window_rect(h)
            area = max(0, r - l) * max(0, b - t)
            if txt and (("열기" in txt) or ("open" in txt.casefold())):
                log(f"[CTRL+T-MULTI] open button hwnd={h} text={txt!r}")
                return h
            if ctrl_id == IDOK and area >= fallback_area:
                fallback_area = area
                fallback_idok = h
        except Exception:
            continue

    if fallback_idok:
        log(f"[CTRL+T-MULTI] open button fallback IDOK hwnd={fallback_idok}")
    else:
        log("[CTRL+T-MULTI] open button not found")
    return int(fallback_idok or 0)


def _wait_for_dialog_close(dialog_hwnd: int, *, sleep_abs: Callable[[float], None], timeout_sec: float) -> bool:
    deadline = time.perf_counter() + max(0.4, float(timeout_sec))
    h = int(dialog_hwnd or 0)
    while time.perf_counter() < deadline:
        if not bool(user32.IsWindow(wintypes.HWND(h))):
            return True
        sleep_abs(0.05)
    return False


def _confirm_dialog_fields_and_submit(
    *,
    dialog_hwnd: int,
    edit_hwnd: int,
    expected_text: str,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float = 3.0,
) -> bool:
    raw_actual = _get_edit_text_via_messages(edit_hwnd)
    actual = _normalize_compare_text(raw_actual)
    expected = _normalize_compare_text(expected_text)
    if actual != expected:
        log(
            "[CTRL+T-MULTI] submit blocked by filename mismatch "
            f"expected={expected_text!r} actual={raw_actual!r}"
        )
        return False

    btn_hwnd = _find_open_button_hwnd(dialog_hwnd, log=log)
    if btn_hwnd:
        try:
            user32.SendMessageW(wintypes.HWND(btn_hwnd), BM_CLICK, 0, 0)
            if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                log("[CTRL+T-MULTI] dialog closed after BM_CLICK")
                return True
        except Exception as e:
            log(f"[CTRL+T-MULTI] BM_CLICK fail hwnd={btn_hwnd} err={e}")

        try:
            l, t, r, b = get_window_rect(btn_hwnd)
            if r > l and b > t:
                x = int((l + r) / 2)
                y = int((t + b) / 2)
                _, _, click = lazy_pywinauto()
                click(coords=(x, y))
                if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                    log("[CTRL+T-MULTI] dialog closed after click")
                    return True
        except Exception as e:
            log(f"[CTRL+T-MULTI] open button click fail err={e}")

    try:
        user32.SendMessageW(wintypes.HWND(dialog_hwnd), WM_COMMAND, IDOK, 0)
        if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
            log("[CTRL+T-MULTI] dialog closed after WM_COMMAND IDOK")
            return True
    except Exception as e:
        log(f"[CTRL+T-MULTI] WM_COMMAND(IDOK) fail err={e}")

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

    names_text = _build_names_text(valid_paths)
    full_paths_text = _build_absolute_paths_text(valid_paths)
    if not full_paths_text:
        return False

    log(f"[CTRL+T-MULTI] names_text={names_text}")
    log(f"[CTRL+T-MULTI] full_paths_text={full_paths_text}")

    try:
        ensure_foreground_chat()
        focus_chat_input_best_effort()
        sleep_abs(0.02)
    except Exception as e:
        log(f"[CTRL+T-MULTI] pre-focus fail: {e}")

    try:
        send_keys_fast("^t")
        dialog_hwnd = _wait_for_open_dialog(
            timeout_sec=max(2.5, _t("after_ctrl_t", 0.20) + 3.0),
            sleep_abs=sleep_abs,
            log=log,
            get_foreground_hwnd_cb=get_foreground_hwnd,
        )
        if not dialog_hwnd:
            _safe_cleanup_after_file_dialog(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
            )
            return False

        edit_hwnd = _find_filename_edit_hwnd(dialog_hwnd, log=log)
        if not edit_hwnd:
            _safe_cleanup_after_file_dialog(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
            )
            return False

        if not _set_edit_text_verified(
            edit_hwnd,
            full_paths_text,
            sleep_abs=sleep_abs,
            log=log,
            timeout_sec=max(1.2, _t("after_paste_path", 0.08) + 1.2),
        ):
            _safe_cleanup_after_file_dialog(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
            )
            return False

        if not _confirm_dialog_fields_and_submit(
            dialog_hwnd=dialog_hwnd,
            edit_hwnd=edit_hwnd,
            expected_text=full_paths_text,
            sleep_abs=sleep_abs,
            log=log,
            submit_timeout_sec=max(3.0, float(timeout_sec)),
        ):
            log("[CTRL+T-MULTI] submit failed or dialog did not close")
            _safe_cleanup_after_file_dialog(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
            )
            return False

        sleep_abs(max(0.15, _t("after_enter_path", 0.25)))

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
