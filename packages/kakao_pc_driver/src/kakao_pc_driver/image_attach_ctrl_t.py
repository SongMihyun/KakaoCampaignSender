# path: src/backend/integrations/kakaotalk/image_attach_ctrl_t.py
from __future__ import annotations

import ctypes
import os
import re
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from kakao_pc_driver.image_attach_cache import get_or_create_temp_png
from kakao_win32.win32_core import (
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

DebugStep = Callable[[str, bool, str, Optional[dict[str, Any]]], None]

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
VK_RETURN = 0x0D
VK_SPACE = 0x20
MK_LBUTTON = 0x0001
EM_SETSEL = 0x00B1
IDOK = 1
EDT1 = 0x0480
CMB13 = 0x047C
OPEN_DIALOG_MIN_SCORE = 900
MULTI_SELECT_WARNING_SNIPPETS = ("여러 항목", "같은 폴더")

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumWindowsProc, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL
user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
user32.GetDlgCtrlID.restype = ctypes.c_int
user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND
user32.SetDlgItemTextW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_wchar_p]
user32.SetDlgItemTextW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL


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
        out.append(ap)
    if len(out) == 1:
        return out[0]
    return " ".join([f'"{ap}"' for ap in out])


def _build_folder_and_names_text(paths: Sequence[str]) -> str:
    shared_parent = _shared_parent_dir(paths)
    names_text = _build_names_text(paths)
    clean_count = len([p for p in paths or [] if str(p or "").strip()])
    if clean_count <= 1 or not shared_parent or not names_text:
        return _build_absolute_paths_text(paths)
    folder = shared_parent.replace('"', "")
    return f'"{folder}" {names_text}'


def _shared_parent_dir(paths: Sequence[str]) -> str:
    parents: list[str] = []
    normalized: set[str] = set()
    for p in paths or []:
        ap = os.path.abspath(str(p or "").strip())
        if not ap:
            continue
        parent = os.path.dirname(ap)
        parents.append(parent)
        normalized.add(os.path.normcase(os.path.normpath(parent)))
    if len(normalized) != 1 or not parents:
        return ""
    return parents[0]


def _build_dialog_input_plan(paths: Sequence[str], *, input_mode: str = "navigate_then_names") -> dict[str, str]:
    names_text = _build_names_text(paths)
    full_paths_text = _build_absolute_paths_text(paths)
    shared_parent = _shared_parent_dir(paths)
    folder_and_names_text = _build_folder_and_names_text(paths)
    mode = str(input_mode or "").strip().lower()
    if mode not in {"absolute_paths", "folder_and_names", "same_folder_names", "navigate_then_names"}:
        mode = "navigate_then_names"
    input_text = full_paths_text
    requires_folder_navigation = False
    if mode == "navigate_then_names":
        if shared_parent and names_text:
            input_text = names_text
            requires_folder_navigation = True
        else:
            mode = "absolute_paths"
    elif mode == "folder_and_names":
        input_text = folder_and_names_text
    elif mode == "same_folder_names":
        input_text = names_text or full_paths_text
    return {
        "input_text": input_text,
        "input_mode": mode,
        "names_text": names_text,
        "full_paths_text": full_paths_text,
        "folder_and_names_text": folder_and_names_text,
        "shared_parent_dir": shared_parent,
        "requires_folder_navigation": "1" if requires_folder_navigation else "",
    }


def _normalize_compare_text(text: str) -> str:
    s = str(text or "").strip().strip('"')
    s = s.replace("/", "\\")
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


def _normalize_filename_match_key(text: str) -> str:
    s = os.path.basename(str(text or "").strip().strip('"'))
    s = s.replace("/", "\\")
    s = re.sub(r"\s+", "", s)
    return s.casefold()


def _filename_match_keys(filename: str) -> set[str]:
    name = os.path.basename(str(filename or "").strip().strip('"'))
    if not name:
        return set()
    stem, _ext = os.path.splitext(name)
    keys = {_normalize_filename_match_key(name)}
    if stem:
        keys.add(_normalize_filename_match_key(stem))
    return {key for key in keys if key}


def _file_dialog_item_matches(item_text: str, filename: str) -> bool:
    item_key = _normalize_filename_match_key(item_text)
    if not item_key:
        return False
    for key in _filename_match_keys(filename):
        if item_key == key or item_key.startswith(key) or key in item_key:
            return True
    return False


def _safe_window_text(el) -> str:
    try:
        return str(el.window_text() or "").strip()
    except Exception:
        return ""


def _emit_debug_step(
    debug_step: Optional[DebugStep],
    step: str,
    *,
    ok: bool,
    detail: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    if not debug_step:
        return
    try:
        debug_step(str(step or ""), bool(ok), str(detail or ""), dict(extra or {}))
    except Exception:
        pass


def _window_extra(hwnd: int) -> dict[str, Any]:
    h = int(hwnd or 0)
    if h <= 0:
        return {
            "active_window_hwnd": 0,
            "active_window_title": "",
            "active_window_class": "",
            "active_window_rect": (0, 0, 0, 0),
            "active_window_size": (0, 0),
        }
    try:
        title = str(get_window_text(h) or "").strip()
    except Exception:
        title = ""
    try:
        cls = str(get_class_name(h) or "").strip()
    except Exception:
        cls = ""
    try:
        l, t, r, b = get_window_rect(h)
    except Exception:
        l = t = r = b = 0
    return {
        "active_window_hwnd": h,
        "active_window_title": title,
        "active_window_class": cls,
        "active_window_rect": (int(l), int(t), int(r), int(b)),
        "active_window_size": (max(0, int(r - l)), max(0, int(b - t))),
    }


def _safe_rect_area(el) -> int:
    try:
        r = el.rectangle()
        w = max(0, int(r.width()))
        h = max(0, int(r.height()))
        return w * h
    except Exception:
        return 0


def _safe_element_hwnd(el) -> int:
    try:
        return int(getattr(getattr(el, "element_info", None), "handle", 0) or 0)
    except Exception:
        return 0


def _safe_top_level_hwnd(el) -> int:
    try:
        parent = el.top_level_parent()
        return _safe_element_hwnd(parent)
    except Exception:
        return 0


def _wait_for_uia_element_gone(el, *, sleep_abs: Callable[[float], None], timeout_sec: float = 1.0) -> bool:
    root_hwnd = _safe_top_level_hwnd(el)
    deadline = time.perf_counter() + max(0.15, float(timeout_sec))
    while time.perf_counter() < deadline:
        if root_hwnd > 0:
            try:
                if not bool(user32.IsWindow(wintypes.HWND(root_hwnd))):
                    return True
            except Exception:
                return True
        try:
            exists = getattr(el, "exists", None)
            if callable(exists) and not bool(exists(timeout=0)):
                return True
            if not _safe_window_text(el):
                return True
        except Exception:
            return True
        sleep_abs(0.05)
    return False


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


def _click_transfer_button_until_gone(
    button,
    *,
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    txt = _safe_window_text(button)

    def _gone(method: str, timeout_sec: float = 1.0) -> tuple[bool, str]:
        if _wait_for_uia_element_gone(button, sleep_abs=sleep_abs, timeout_sec=timeout_sec):
            log(f"[FILE_SEND][CLICK_CONFIRMED] method={method} text={txt!r}")
            return True, method
        log(f"[FILE_SEND][CLICK_STILL_OPEN] method={method} text={txt!r}")
        return False, method

    try:
        log(f"[FILE_SEND][CLICK_TRY] method=invoke_wait text={txt!r}")
        button.invoke()
        sleep_abs(0.10)
        ok, method = _gone("invoke")
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method=invoke_wait text={txt!r} err={e}")

    try:
        log(f"[FILE_SEND][CLICK_TRY] method=click_input_wait text={txt!r}")
        button.click_input()
        sleep_abs(0.10)
        ok, method = _gone("click_input")
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method=click_input_wait text={txt!r} err={e}")

    try:
        rect = button.rectangle()
        x = int((int(rect.left) + int(rect.right)) / 2)
        y = int((int(rect.top) + int(rect.bottom)) / 2)
        log(f"[FILE_SEND][CLICK_TRY] method=coordinate_click_wait text={txt!r} coords=({x},{y})")
        _, _, click = lazy_pywinauto()
        click(coords=(x, y))
        sleep_abs(0.12)
        ok, method = _gone("coordinate_click", timeout_sec=1.2)
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method=coordinate_click_wait text={txt!r} err={e}")

    try:
        log(f"[FILE_SEND][CLICK_TRY] method=focus_enter_wait text={txt!r}")
        button.set_focus()
        sleep_abs(0.06)
        send_keys_fast("{ENTER}")
        sleep_abs(0.12)
        ok, method = _gone("focus_enter", timeout_sec=1.2)
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method=focus_enter_wait text={txt!r} err={e}")

    try:
        log(f"[FILE_SEND][CLICK_TRY] method=focus_space_wait text={txt!r}")
        button.set_focus()
        sleep_abs(0.06)
        send_keys_fast("{SPACE}")
        sleep_abs(0.12)
        ok, method = _gone("focus_space", timeout_sec=1.2)
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method=focus_space_wait text={txt!r} err={e}")

    if _click_uia_element(button, sleep_abs=sleep_abs, log=log):
        ok, method = _gone("legacy_uia_click", timeout_sec=1.2)
        if ok:
            return ok, method

    root_hwnd = _safe_top_level_hwnd(button)
    ok, method = _click_transfer_window_bottom_area_until_gone(
        root_hwnd,
        send_keys_fast=send_keys_fast,
        sleep_abs=sleep_abs,
        log=log,
        method_prefix="button_root",
    )
    if ok:
        return ok, method

    return False, "not_closed"


def _click_transfer_window_bottom_area_until_gone(
    window_hwnd: int,
    *,
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    method_prefix: str = "window",
) -> tuple[bool, str]:
    hwnd = int(window_hwnd or 0)
    if hwnd <= 0:
        return False, f"{method_prefix}_invalid_hwnd"

    try:
        if not bool(user32.IsWindow(wintypes.HWND(hwnd))):
            return False, f"{method_prefix}_window_missing"
    except Exception:
        return False, f"{method_prefix}_window_missing"

    def _gone(method: str, timeout_sec: float = 1.2) -> tuple[bool, str]:
        if _wait_for_dialog_close(hwnd, sleep_abs=sleep_abs, timeout_sec=timeout_sec):
            log(f"[FILE_SEND][CLICK_CONFIRMED] method={method} hwnd={hwnd}")
            return True, method
        log(f"[FILE_SEND][CLICK_STILL_OPEN] method={method} hwnd={hwnd}")
        return False, method

    try:
        l, t, r, b = get_window_rect(hwnd)
        if r <= l or b <= t:
            return False, f"{method_prefix}_bad_rect"
        x = int((l + r) / 2)
        # Kakao's file-transfer button is a wide split button near the bottom.
        # Click several nearby vertical points because PC scaling changes the exact center.
        y_candidates = [
            int(b - max(34, min(52, (b - t) * 0.13))),
            int(b - max(42, min(64, (b - t) * 0.17))),
            int(b - max(26, min(44, (b - t) * 0.10))),
        ]
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method={method_prefix}_bottom_area_rect hwnd={hwnd} err={e}")
        return False, f"{method_prefix}_rect_failed"

    for idx, y in enumerate(y_candidates):
        try:
            user32.SetForegroundWindow(wintypes.HWND(hwnd))
            sleep_abs(0.06)
        except Exception:
            pass
        try:
            log(f"[FILE_SEND][CLICK_TRY] method={method_prefix}_bottom_area_{idx} hwnd={hwnd} coords=({x},{y})")
            _, _, click = lazy_pywinauto()
            click(coords=(x, int(y)))
            sleep_abs(0.14)
            ok, method = _gone(f"{method_prefix}_bottom_area_{idx}", timeout_sec=1.25)
            if ok:
                return ok, method
        except Exception as e:
            log(f"[FILE_SEND][CLICK_FAIL] method={method_prefix}_bottom_area_{idx} hwnd={hwnd} err={e}")

    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        sleep_abs(0.06)
        log(f"[FILE_SEND][CLICK_TRY] method={method_prefix}_window_enter hwnd={hwnd}")
        send_keys_fast("{ENTER}")
        sleep_abs(0.14)
        ok, method = _gone(f"{method_prefix}_window_enter", timeout_sec=1.25)
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method={method_prefix}_window_enter hwnd={hwnd} err={e}")

    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        sleep_abs(0.06)
        log(f"[FILE_SEND][CLICK_TRY] method={method_prefix}_window_space hwnd={hwnd}")
        send_keys_fast("{SPACE}")
        sleep_abs(0.14)
        ok, method = _gone(f"{method_prefix}_window_space", timeout_sec=1.25)
        if ok:
            return ok, method
    except Exception as e:
        log(f"[FILE_SEND][CLICK_FAIL] method={method_prefix}_window_space hwnd={hwnd} err={e}")

    return False, f"{method_prefix}_not_closed"


def _extract_transfer_count(text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*개\s*전송", str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _collect_uia_texts_for_hwnd(hwnd: int, *, limit: int = 120) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        texts.append(text)

    try:
        Desktop, _, _ = lazy_pywinauto()
        root = Desktop(backend="uia").window(handle=int(hwnd or 0))
        _add(_safe_window_text(root))
        try:
            descendants = root.descendants()
        except Exception:
            descendants = []
        for el in descendants:
            if len(texts) >= limit:
                break
            _add(_safe_window_text(el))
    except Exception:
        pass
    return texts


def _probable_kakao_file_transfer_window_meta(
    hwnd: int,
    *,
    expected_file_count: int = 0,
    collect_texts: bool = True,
) -> Optional[dict[str, Any]]:
    h = int(hwnd or 0)
    if h <= 0:
        return None
    try:
        if not bool(user32.IsWindowVisible(wintypes.HWND(h))):
            return None
        cls = str(get_class_name(h) or "").strip()
        title = str(get_window_text(h) or "").strip()
        l, t, r, b = get_window_rect(h)
    except Exception:
        return None

    width = max(0, int(r - l))
    height = max(0, int(b - t))
    if width <= 0 or height <= 0:
        return None

    is_eva = cls.startswith("EVA_")
    is_small_float = 180 <= width <= 520 and 170 <= height <= 720
    if not is_eva and "파일 전송" not in title and "Kakao" not in title:
        return None

    texts = _collect_uia_texts_for_hwnd(h, limit=120) if collect_texts else []
    blob = "\n".join([title, *texts])
    expected = int(expected_file_count or 0)
    has_expected_count = expected > 0 and any(_extract_transfer_count(t) == expected for t in texts)
    has_any_transfer_count = any(_extract_transfer_count(t) is not None for t in texts)
    has_file_transfer_text = "파일 전송" in blob
    has_attachment_hint = ("attach_" in blob) or (".jpg" in blob.lower()) or (".png" in blob.lower()) or (".jpeg" in blob.lower())

    if not (
        has_file_transfer_text
        or has_expected_count
        or has_any_transfer_count
        or (is_eva and is_small_float and has_attachment_hint)
    ):
        return None

    return {
        "window_hwnd": h,
        "window_title": title,
        "window_class": cls,
        "window_rect": (int(l), int(t), int(r), int(b)),
        "window_size": (width, height),
        "is_small_float": bool(is_small_float),
        "has_file_transfer_text": bool(has_file_transfer_text),
        "has_expected_count": bool(has_expected_count),
        "has_any_transfer_count": bool(has_any_transfer_count),
        "has_attachment_hint": bool(has_attachment_hint),
        "texts": texts[:40],
    }


def _find_probable_kakao_file_transfer_window(
    *,
    chat_hwnd: int,
    expected_file_count: int,
) -> tuple[int, dict[str, Any]]:
    ordered: list[int] = []
    seen: set[int] = set()

    def _add(hwnd: int) -> None:
        h = int(hwnd or 0)
        if h <= 0 or h in seen:
            return
        seen.add(h)
        ordered.append(h)

    try:
        _add(_root_hwnd(get_foreground_hwnd()))
    except Exception:
        pass
    try:
        _add(_root_hwnd(int(chat_hwnd or 0)))
    except Exception:
        pass
    for hwnd in _iter_top_windows():
        _add(hwnd)

    for hwnd in ordered:
        meta = _probable_kakao_file_transfer_window_meta(
            hwnd,
            expected_file_count=int(expected_file_count or 0),
            collect_texts=True,
        )
        if meta:
            return int(hwnd), meta
    return 0, {}


def _collect_dialog_texts(hwnd: int, *, limit: int = 80) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        texts.append(text)

    try:
        _add(get_window_text(int(hwnd or 0)))
    except Exception:
        pass

    for child in _iter_child_windows(int(hwnd or 0), recursive=True):
        if len(texts) >= limit:
            break
        try:
            _add(get_window_text(child))
        except Exception:
            continue

    return texts


def _find_dialog_confirm_button(dialog_hwnd: int) -> int:
    fallback = 0
    for child in _iter_child_windows(int(dialog_hwnd or 0), recursive=True):
        try:
            if str(get_class_name(child) or "") != "Button":
                continue
            text = str(get_window_text(child) or "").strip()
            ctrl_id = int(user32.GetDlgCtrlID(wintypes.HWND(child)) or 0)
            if text in {"확인", "OK", "&OK"}:
                return int(child)
            if ctrl_id == IDOK:
                fallback = int(child)
        except Exception:
            continue
    return int(fallback or 0)


def _multi_select_warning_meta(hwnd: int) -> Optional[dict[str, Any]]:
    h = int(hwnd or 0)
    if h <= 0:
        return None
    try:
        if str(get_class_name(h) or "") != "#32770":
            return None
        if not bool(user32.IsWindowVisible(wintypes.HWND(h))):
            return None
    except Exception:
        return None

    texts = _collect_dialog_texts(h)
    blob = "\n".join(texts)
    if not all(snippet in blob for snippet in MULTI_SELECT_WARNING_SNIPPETS):
        return None

    return {
        "warning_hwnd": h,
        "active_window_class": "#32770",
        "message": next((t for t in texts if all(s in t for s in MULTI_SELECT_WARNING_SNIPPETS)), blob[:500]),
        "texts": texts[:12],
        "confirm_button_hwnd": _find_dialog_confirm_button(h),
    }


def _find_multi_select_warning_dialog(
    *,
    get_foreground_hwnd_cb: Optional[Callable[[], int]] = None,
) -> Optional[dict[str, Any]]:
    ordered: list[int] = []
    seen: set[int] = set()

    try:
        fg = int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0)
        root = _root_hwnd(fg)
        if root > 0:
            ordered.append(root)
            seen.add(root)
    except Exception:
        pass

    for hwnd in _iter_top_windows():
        if hwnd in seen:
            continue
        ordered.append(hwnd)
        seen.add(hwnd)

    for hwnd in ordered:
        meta = _multi_select_warning_meta(hwnd)
        if meta:
            return meta
    return None


def _confirm_warning_button_until_closed(
    *,
    warning_hwnd: int,
    button_hwnd: int,
    send_keys_fast: Optional[Callable[[str], None]],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    warning = int(warning_hwnd or 0)
    button = int(button_hwnd or 0)
    if warning <= 0 or button <= 0:
        return False, "invalid_hwnd"

    def _closed(timeout_sec: float = 0.45) -> bool:
        return _wait_for_dialog_close(warning, sleep_abs=sleep_abs, timeout_sec=timeout_sec)

    def _button_lparam() -> int:
        return (8 & 0xFFFF) | ((8 & 0xFFFF) << 16)

    try:
        user32.SetForegroundWindow(wintypes.HWND(warning))
        sleep_abs(0.06)
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning foreground fail err={e}")

    if send_keys_fast is not None:
        try:
            send_keys_fast("{ENTER}")
            if _closed(0.55):
                return True, "focused_enter"
        except Exception as e:
            log(f"[CTRL+T-MULTI] warning focused ENTER fail hwnd={warning} err={e}")

    try:
        user32.SetFocus(wintypes.HWND(button))
        sleep_abs(0.03)
        user32.SendMessageW(wintypes.HWND(button), WM_KEYDOWN, VK_RETURN, 0)
        sleep_abs(0.03)
        user32.SendMessageW(wintypes.HWND(button), WM_KEYUP, VK_RETURN, 0)
        if _closed(0.55):
            return True, "button_return_key_message"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning button RETURN message fail hwnd={button} err={e}")

    try:
        user32.SetFocus(wintypes.HWND(button))
        sleep_abs(0.03)
        user32.SendMessageW(wintypes.HWND(button), WM_KEYDOWN, VK_SPACE, 0)
        sleep_abs(0.03)
        user32.SendMessageW(wintypes.HWND(button), WM_KEYUP, VK_SPACE, 0)
        if _closed(0.55):
            return True, "button_space_key_message"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning button SPACE message fail hwnd={button} err={e}")

    try:
        user32.SendMessageW(wintypes.HWND(button), BM_CLICK, 0, 0)
        if _closed(0.55):
            return True, "bm_click"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning BM_CLICK fail hwnd={button} err={e}")

    try:
        user32.SendMessageW(wintypes.HWND(warning), WM_COMMAND, IDOK, button)
        if _closed(0.55):
            return True, "wm_command_idok"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning WM_COMMAND IDOK fail hwnd={warning} err={e}")

    try:
        user32.PostMessageW(wintypes.HWND(warning), WM_COMMAND, IDOK, button)
        if _closed(0.55):
            return True, "post_wm_command_idok"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning PostMessage IDOK fail hwnd={warning} err={e}")

    try:
        user32.SendMessageW(wintypes.HWND(button), WM_LBUTTONDOWN, MK_LBUTTON, _button_lparam())
        sleep_abs(0.04)
        user32.SendMessageW(wintypes.HWND(button), WM_LBUTTONUP, 0, _button_lparam())
        if _closed(0.55):
            return True, "button_mouse_message"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning button mouse message fail hwnd={button} err={e}")

    try:
        Desktop, _, _ = lazy_pywinauto()
        btn = Desktop(backend="uia").window(handle=button)
        if _click_uia_element(btn, sleep_abs=sleep_abs, log=log):
            if _closed(0.75):
                return True, "uia_button_click"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning UIA button click fail hwnd={button} err={e}")

    try:
        l, t, r, b = get_window_rect(button)
        if r > l and b > t:
            _, _, click = lazy_pywinauto()
            click(coords=(int((l + r) / 2), int((t + b) / 2)))
            if _closed(0.9):
                return True, "coordinate_click"
    except Exception as e:
        log(f"[CTRL+T-MULTI] warning confirm click fallback fail err={e}")

    if send_keys_fast is not None:
        try:
            user32.SetForegroundWindow(wintypes.HWND(warning))
            sleep_abs(0.05)
            send_keys_fast("{SPACE}")
            if _closed(0.55):
                return True, "focused_space"
        except Exception as e:
            log(f"[CTRL+T-MULTI] warning focused SPACE fail hwnd={warning} err={e}")

        try:
            user32.SetForegroundWindow(wintypes.HWND(warning))
            sleep_abs(0.05)
            send_keys_fast("{ENTER}")
            if _closed(0.75):
                return True, "focused_enter_retry"
        except Exception as e:
            log(f"[CTRL+T-MULTI] warning focused ENTER retry fail hwnd={warning} err={e}")

    return False, "not_closed"


def _confirm_recoverable_multi_select_warning(
    *,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    debug_step: Optional[DebugStep],
    expected_file_count: int,
    send_keys_fast: Optional[Callable[[str], None]] = None,
    get_foreground_hwnd_cb: Optional[Callable[[], int]] = None,
    timeout_sec: float = 0.8,
) -> tuple[bool, bool]:
    deadline = time.perf_counter() + max(0.05, float(timeout_sec))
    meta: Optional[dict[str, Any]] = None
    while time.perf_counter() < deadline:
        meta = _find_multi_select_warning_dialog(get_foreground_hwnd_cb=get_foreground_hwnd_cb)
        if meta:
            break
        sleep_abs(0.05)

    if not meta:
        return False, False

    meta = dict(meta)
    meta["attachment_count"] = int(expected_file_count or 0)
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_MULTI_SELECT_WARNING_DETECTED",
        ok=True,
        detail="recoverable multi-file warning detected",
        extra=meta,
    )
    log(
        "[CTRL+T-MULTI] recoverable multi-select warning detected "
        f"hwnd={meta.get('warning_hwnd')} message={meta.get('message')!r}"
    )

    warning_hwnd = int(meta.get("warning_hwnd") or 0)
    button_hwnd = int(meta.get("confirm_button_hwnd") or 0)
    if warning_hwnd <= 0 or button_hwnd <= 0:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_MULTI_SELECT_WARNING_CONFIRMED",
            ok=False,
            detail="confirm button was not found on recoverable warning",
            extra=meta,
        )
        return True, False

    confirmed, method = _confirm_warning_button_until_closed(
        warning_hwnd=warning_hwnd,
        button_hwnd=button_hwnd,
        send_keys_fast=send_keys_fast,
        sleep_abs=sleep_abs,
        log=log,
    )
    meta["confirm_method"] = method
    if not confirmed:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_MULTI_SELECT_WARNING_CONFIRMED",
            ok=False,
            detail="recoverable warning confirm failed",
            extra=meta,
        )
        return True, False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_MULTI_SELECT_WARNING_CONFIRMED",
        ok=True,
        detail="recoverable warning confirmed",
        extra=meta,
    )
    log("[CTRL+T-MULTI] recoverable multi-select warning confirmed")
    return True, True


def _find_send_button_in_chat_surface(
    *,
    chat_hwnd: int,
    log: Callable[[str], None],
    expected_file_count: int = 0,
    debug_candidates: bool = True,
):
    """
    카카오 채팅창(UIA 트리) 안에서
    - '4개 전송'
    - '전송'
    버튼을 직접 찾는다.
    """
    try:
        Desktop, _, _ = lazy_pywinauto()
    except Exception as e:
        log(f"[FILE_SEND][DESKTOP_ATTACH_FAIL] err={e}")
        return None

    handles: list[int] = []
    seen_handles: set[int] = set()

    def _add_handle(hwnd: int) -> None:
        h = int(hwnd or 0)
        if h <= 0 or h in seen_handles:
            return
        seen_handles.add(h)
        handles.append(h)

    _add_handle(int(chat_hwnd or 0))
    try:
        _add_handle(_root_hwnd(get_foreground_hwnd()))
    except Exception:
        pass
    for hwnd in _iter_top_windows():
        try:
            title = str(get_window_text(hwnd) or "")
            cls = str(get_class_name(hwnd) or "")
            l, t, r, b = get_window_rect(hwnd)
            width = max(0, int(r - l))
            height = max(0, int(b - t))
            is_small_eva = cls.startswith("EVA_") and 180 <= width <= 520 and 170 <= height <= 720
            probable_meta = _probable_kakao_file_transfer_window_meta(
                hwnd,
                expected_file_count=int(expected_file_count or 0),
                collect_texts=False,
            )
            if probable_meta or is_small_eva or "파일 전송" in title or "카카오" in title or "Kakao" in title:
                _add_handle(hwnd)
        except Exception:
            continue

    exact_count: list[Any] = []
    preferred: list[Any] = []
    fallback: list[Any] = []

    max_debug = 40
    debug_idx = 0

    for root_hwnd in handles:
        try:
            root = Desktop(backend="uia").window(handle=int(root_hwnd))
            candidates = _iter_button_like_descendants(root)
        except Exception as e:
            log(f"[FILE_SEND][ROOT_ATTACH_FAIL] hwnd={root_hwnd} err={e}")
            continue

        for el in candidates:
            try:
                txt = _safe_window_text(el)
                area = _safe_rect_area(el)

                if debug_candidates and debug_idx < max_debug:
                    try:
                        ctrl_type = getattr(getattr(el, "element_info", None), "control_type", "")
                    except Exception:
                        ctrl_type = ""
                    log(
                        "[FILE_SEND][CANDIDATE] "
                        f"idx={debug_idx} root={root_hwnd} text={txt!r} area={area} type={ctrl_type!r}"
                    )
                    debug_idx += 1

                if not txt:
                    continue

                transfer_count = _extract_transfer_count(txt)
                if transfer_count is not None:
                    if int(expected_file_count or 0) > 0 and transfer_count == int(expected_file_count):
                        exact_count.append((area, el))
                        continue
                    preferred.append((area, el))
                    continue

                if txt == "전송":
                    if int(expected_file_count or 0) <= 1:
                        preferred.append((area, el))
                    continue

                if "전송" in txt:
                    if int(expected_file_count or 0) > 1:
                        continue
                    fallback.append((area, el))
                    continue
            except Exception as e:
                log(f"[FILE_SEND][CANDIDATE_ERR] err={e}")
                continue

    for label, matches in (("exact_count", exact_count), ("preferred", preferred), ("fallback", fallback)):
        if not matches:
            continue
        matches.sort(key=lambda x: x[0], reverse=True)
        btn = matches[0][1]
        try:
            log(f"[FILE_SEND][MATCH_PICK] {label} text={_safe_window_text(btn)!r}")
        except Exception:
            pass
        return btn

    return None


def _wait_for_kakao_file_transfer_button(
    *,
    chat_hwnd: int,
    expected_file_count: int,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    debug_step: Optional[DebugStep],
    timeout_sec: float,
) -> tuple[Optional[Any], dict[str, Any], str]:
    deadline = time.perf_counter() + max(0.8, float(timeout_sec))
    expected = int(expected_file_count or 0)
    last_meta: dict[str, Any] = {
        "chat_hwnd": int(chat_hwnd or 0),
        "expected_file_count": expected,
    }
    mismatch_meta: Optional[dict[str, Any]] = None
    attempt = 0

    while time.perf_counter() < deadline:
        button = _find_send_button_in_chat_surface(
            chat_hwnd=int(chat_hwnd or 0),
            log=log,
            expected_file_count=expected,
            debug_candidates=(attempt == 0),
        )
        attempt += 1
        if button is None:
            sleep_abs(0.08)
            continue

        text = _safe_window_text(button)
        actual_count = _extract_transfer_count(text)
        meta = {
            "chat_hwnd": int(chat_hwnd or 0),
            "expected_file_count": expected,
            "button_text": text,
            "actual_file_count": actual_count,
        }
        last_meta = meta

        if expected > 1 and actual_count != expected:
            mismatch_meta = meta
            sleep_abs(0.10)
            continue
        if expected == 1 and actual_count not in (None, 1):
            mismatch_meta = meta
            sleep_abs(0.10)
            continue

        _emit_debug_step(
            debug_step,
            "KAKAO_FILE_TRANSFER_DIALOG_DETECTED",
            ok=True,
            detail="Kakao file transfer dialog detected",
            extra=meta,
        )
        return button, meta, ""

    if mismatch_meta is not None:
        _emit_debug_step(
            debug_step,
            "KAKAO_FILE_TRANSFER_COUNT_MISMATCH",
            ok=False,
            detail="Kakao file transfer count did not match expected attachments",
            extra=mismatch_meta,
        )
        return None, mismatch_meta, "count_mismatch"

    _emit_debug_step(
        debug_step,
        "KAKAO_FILE_TRANSFER_DIALOG_DETECTED",
        ok=False,
        detail="Kakao file transfer dialog was not detected",
        extra=last_meta,
    )
    return None, last_meta, "dialog_not_found"


def send_files_dialog_hook(
    *,
    chat_hwnd: int,
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    timeout_sec: float = 2.5,
    expected_file_count: int = 0,
    debug_step: Optional[DebugStep] = None,
) -> bool:
    """
    현재 환경 전용 최적화:
    파일 전송 UI를 먼저 검증하고, 확인된 전송 버튼을 클릭한다.
    실패/잔류창 상황까지 고려해 정리 로직 포함.
    """
    try:
        log(f"[FILE_SEND][VERIFY_BEGIN] hwnd={chat_hwnd} expected={expected_file_count}")

        _emit_debug_step(
            debug_step,
            "KAKAO_FILE_TRANSFER_DIALOG_WAIT",
            ok=True,
            detail="wait for Kakao file transfer dialog",
            extra={
                "chat_hwnd": int(chat_hwnd or 0),
                "expected_file_count": int(expected_file_count or 0),
                "timeout_ms": int(max(2.0, float(timeout_sec)) * 1000),
            },
        )

        button, meta, failure = _wait_for_kakao_file_transfer_button(
            chat_hwnd=int(chat_hwnd or 0),
            expected_file_count=int(expected_file_count or 0),
            sleep_abs=sleep_abs,
            log=log,
            debug_step=debug_step,
            timeout_sec=max(2.0, float(timeout_sec)),
        )
        if button is None:
            transfer_hwnd, transfer_meta = _find_probable_kakao_file_transfer_window(
                chat_hwnd=int(chat_hwnd or 0),
                expected_file_count=int(expected_file_count or 0),
            )
            if transfer_hwnd > 0:
                fallback_meta = {
                    **dict(meta or {}),
                    "fallback_transfer_window": transfer_meta,
                    "click_method": "transfer_window_bottom_area",
                }
                _emit_debug_step(
                    debug_step,
                    "KAKAO_FILE_TRANSFER_DIALOG_DETECTED",
                    ok=True,
                    detail="Kakao file transfer dialog detected by floating window fallback",
                    extra=fallback_meta,
                )
                clicked, click_method = _click_transfer_window_bottom_area_until_gone(
                    transfer_hwnd,
                    send_keys_fast=send_keys_fast,
                    sleep_abs=sleep_abs,
                    log=log,
                    method_prefix="floating_window",
                )
                fallback_meta["click_method"] = click_method
                if clicked:
                    _emit_debug_step(
                        debug_step,
                        "KAKAO_FILE_TRANSFER_SEND_BUTTON_CLICKED",
                        ok=True,
                        detail="Kakao file transfer send button clicked by floating window fallback",
                        extra=fallback_meta,
                    )
                    _safe_cleanup_after_file_dialog(
                        prefer_hwnd=int(chat_hwnd or 0),
                        sleep_abs=sleep_abs,
                        log=log,
                    )
                    log("[FILE_SEND][VERIFY_OK] file transfer floating window clicked")
                    return True

                _emit_debug_step(
                    debug_step,
                    "KAKAO_FILE_TRANSFER_BUTTON_NOT_FOUND",
                    ok=False,
                    detail="Kakao file transfer floating window click failed",
                    extra=fallback_meta,
                )
                log(f"[FILE_SEND][VERIFY_FAIL] floating window click failed meta={fallback_meta}")
                return False

            log(f"[FILE_SEND][VERIFY_FAIL] reason={failure} meta={meta}")
            return False

        _emit_debug_step(
            debug_step,
            "KAKAO_FILE_TRANSFER_SEND_BUTTON_FOUND",
            ok=True,
            detail="Kakao file transfer send button found",
            extra=meta,
        )

        clicked, click_method = _click_transfer_button_until_gone(
            button,
            send_keys_fast=send_keys_fast,
            sleep_abs=sleep_abs,
            log=log,
        )
        meta = dict(meta)
        meta["click_method"] = click_method

        if not clicked:
            try:
                log("[FILE_SEND][CLICK_FALLBACK] TAB->TAB->ENTER")
                send_keys_fast("{TAB}")
                sleep_abs(0.05)
                send_keys_fast("{TAB}")
                sleep_abs(0.05)
                send_keys_fast("{ENTER}")
                sleep_abs(0.18)
                if not _wait_for_uia_element_gone(button, sleep_abs=sleep_abs, timeout_sec=1.0):
                    raise RuntimeError("file transfer dialog still open after TAB fallback")
                meta["click_method"] = "tab_tab_enter"
            except Exception as e:
                log(f"[FILE_SEND][CLICK_FALLBACK_FAIL] err={e}")
                _emit_debug_step(
                    debug_step,
                    "KAKAO_FILE_TRANSFER_BUTTON_NOT_FOUND",
                    ok=False,
                    detail="Kakao file transfer button click failed",
                    extra=meta,
                )
                return False

        _emit_debug_step(
            debug_step,
            "KAKAO_FILE_TRANSFER_SEND_BUTTON_CLICKED",
            ok=True,
            detail="Kakao file transfer send button clicked",
            extra=meta,
        )

        _safe_cleanup_after_file_dialog(
            prefer_hwnd=int(chat_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
        )

        log("[FILE_SEND][VERIFY_OK] file transfer button clicked")
        return True

    except Exception as e:
        log(f"[FILE_SEND][VERIFY_FAIL] err={e}")

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


def _safe_hwnd_rect(hwnd: int) -> tuple[int, int, int, int]:
    try:
        l, t, r, b = get_window_rect(int(hwnd or 0))
        return int(l), int(t), int(r), int(b)
    except Exception:
        return 0, 0, 0, 0


def _safe_dialog_item(hwnd: int, ctrl_id: int) -> int:
    try:
        return int(user32.GetDlgItem(wintypes.HWND(int(hwnd or 0)), int(ctrl_id)) or 0)
    except Exception:
        return 0


def _title_looks_like_open_dialog(title: str) -> bool:
    value = str(title or "").strip()
    folded = value.casefold()
    return ("open" in folded) or ("\uc5f4\uae30" in value)


def _summarize_dialog_children(hwnd: int) -> dict[str, Any]:
    children = _iter_child_windows(hwnd, recursive=True)
    class_counts: dict[str, int] = {}
    text_hits: list[dict[str, Any]] = []
    for child in children:
        try:
            cls = str(get_class_name(child) or "").strip()
            if cls:
                class_counts[cls] = class_counts.get(cls, 0) + 1
            title = str(get_window_text(child) or "").strip()
            if title and (
                _title_looks_like_open_dialog(title)
                or "file name" in title.casefold()
                or "\ud30c\uc77c" in title
                or "\uc774\ub984" in title
            ):
                text_hits.append(
                    {
                        "hwnd": int(child),
                        "class": cls,
                        "text": title[:80],
                        "ctrl_id": int(user32.GetDlgCtrlID(wintypes.HWND(child)) or 0),
                    }
                )
        except Exception:
            continue

    direct_items: list[dict[str, Any]] = []
    for ctrl_id, name in ((EDT1, "EDT1"), (CMB13, "CMB13"), (IDOK, "IDOK")):
        item = _safe_dialog_item(hwnd, ctrl_id)
        if not item:
            continue
        try:
            item_cls = str(get_class_name(item) or "").strip()
        except Exception:
            item_cls = ""
        try:
            item_text = str(get_window_text(item) or "").strip()
        except Exception:
            item_text = ""
        direct_items.append(
            {
                "name": name,
                "ctrl_id": int(ctrl_id),
                "hwnd": int(item),
                "class": item_cls,
                "text": item_text[:80],
            }
        )

    return {
        "child_count": len(children),
        "class_counts": dict(sorted(class_counts.items())[:30]),
        "text_hits": text_hits[:8],
        "direct_items": direct_items,
    }


def _score_open_dialog_candidate(hwnd: int, *, foreground_root: int = 0) -> tuple[int, dict[str, Any]]:
    h = int(hwnd or 0)
    if h <= 0:
        return 0, {"hwnd": h, "reason": "empty hwnd"}

    try:
        cls = str(get_class_name(h) or "").strip()
    except Exception:
        cls = ""
    try:
        title = str(get_window_text(h) or "").strip()
    except Exception:
        title = ""
    try:
        visible = bool(user32.IsWindowVisible(wintypes.HWND(h)))
    except Exception:
        visible = False

    l, t, r, b = _safe_hwnd_rect(h)
    width = max(0, r - l)
    height = max(0, b - t)
    area = width * height

    meta: dict[str, Any] = {
        "hwnd": h,
        "title": title,
        "class": cls,
        "visible": visible,
        "rect": (l, t, r, b),
        "size": (width, height),
        "area": area,
        "foreground_root": int(foreground_root or 0),
        "is_foreground_root": h == int(foreground_root or 0),
    }
    if cls != "#32770" or not visible:
        meta["reason"] = "not visible #32770 dialog"
        return 0, meta

    summary = _summarize_dialog_children(h)
    meta.update(summary)

    class_counts = summary.get("class_counts", {})
    direct_items = summary.get("direct_items", [])
    direct_ids = {int(item.get("ctrl_id") or 0) for item in direct_items}
    direct_classes = {str(item.get("class") or "") for item in direct_items}
    child_count = int(summary.get("child_count") or 0)
    has_edit = bool(class_counts.get("Edit") or "Edit" in direct_classes)
    has_combo = bool(
        class_counts.get("ComboBox")
        or class_counts.get("ComboBoxEx32")
        or "ComboBox" in direct_classes
        or "ComboBoxEx32" in direct_classes
    )
    has_filename_item = bool((EDT1 in direct_ids) or (CMB13 in direct_ids) or has_edit or has_combo)
    has_open_button = IDOK in direct_ids
    has_file_view = any(
        class_counts.get(name)
        for name in (
            "DirectUIHWND",
            "SHELLDLL_DefView",
            "SysListView32",
            "DUIViewWndClassName",
        )
    )

    score = 0
    if area >= 80_000:
        score += min(2200, area // 500)
    else:
        score -= 600
    if _title_looks_like_open_dialog(title):
        score += 5000
    elif title:
        score += 120
    else:
        score -= 80
    if h == int(foreground_root or 0):
        score += 400
    if has_filename_item:
        score += 4200
    if has_open_button:
        score += 900
    if has_file_view:
        score += 1200
    if child_count >= 6:
        score += min(1200, child_count * 25)

    meta.update(
        {
            "score": int(score),
            "has_filename_item": bool(has_filename_item),
            "has_open_button": bool(has_open_button),
            "has_file_view": bool(has_file_view),
        }
    )
    return int(score), meta


def _brief_open_dialog_candidate(meta: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hwnd": int(meta.get("hwnd") or 0),
        "score": int(meta.get("score") or 0),
        "title": str(meta.get("title") or "")[:80],
        "class": str(meta.get("class") or ""),
        "visible": bool(meta.get("visible")),
        "rect": meta.get("rect") or (0, 0, 0, 0),
        "size": meta.get("size") or (0, 0),
        "child_count": int(meta.get("child_count") or 0),
        "has_filename_item": bool(meta.get("has_filename_item")),
        "has_open_button": bool(meta.get("has_open_button")),
        "has_file_view": bool(meta.get("has_file_view")),
        "direct_items": list(meta.get("direct_items") or [])[:6],
    }


def _has_open_dialog_signal(meta: Mapping[str, Any]) -> bool:
    return bool(
        meta.get("has_filename_item")
        or meta.get("has_open_button")
        or meta.get("has_file_view")
        or _title_looks_like_open_dialog(str(meta.get("title") or ""))
    )


def _looks_like_open_dialog(hwnd: int) -> bool:
    score, meta = _score_open_dialog_candidate(hwnd)
    return score >= OPEN_DIALOG_MIN_SCORE and _has_open_dialog_signal(meta)
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
) -> tuple[int, dict[str, Any]]:
    deadline = time.perf_counter() + max(0.8, float(timeout_sec))
    last_fg_root = 0
    last_candidates: list[dict[str, Any]] = []
    while time.perf_counter() < deadline:
        fg = int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0)
        fg_root = _root_hwnd(fg)
        last_fg_root = fg_root
        seen: set[int] = set()
        scored: list[tuple[int, int, dict[str, Any]]] = []
        if fg_root > 0:
            seen.add(fg_root)
            score, meta = _score_open_dialog_candidate(fg_root, foreground_root=fg_root)
            if str(meta.get("class") or "") == "#32770":
                scored.append((score, fg_root, meta))

        for h in _iter_top_windows():
            if h in seen:
                continue
            seen.add(h)
            score, meta = _score_open_dialog_candidate(h, foreground_root=fg_root)
            if str(meta.get("class") or "") == "#32770":
                scored.append((score, h, meta))

        scored.sort(key=lambda item: item[0], reverse=True)
        last_candidates = [_brief_open_dialog_candidate(item[2]) for item in scored[:5]]
        if scored and int(scored[0][0]) >= OPEN_DIALOG_MIN_SCORE and _has_open_dialog_signal(scored[0][2]):
            score, h, meta = scored[0]
            log(
                "[CTRL+T-MULTI] open dialog selected "
                f"hwnd={h} score={score} title={meta.get('title')!r} "
                f"rect={meta.get('rect')} children={meta.get('child_count')}"
            )
            meta["selected_from"] = "scored_dialog_candidates"
            meta["candidate_count"] = len(scored)
            meta["top_candidates"] = last_candidates
            return int(h), meta
        sleep_abs(0.05)

    log(f"[CTRL+T-MULTI] open dialog not found fg_root={last_fg_root} candidates={last_candidates}")
    return 0, {"foreground_root": int(last_fg_root or 0), "top_candidates": last_candidates}


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
    for ctrl_id, name in ((EDT1, "EDT1"), (CMB13, "CMB13")):
        try:
            item = _safe_dialog_item(dialog_hwnd, ctrl_id)
            if item:
                item_cls = str(get_class_name(item) or "")
                if item_cls == "Edit":
                    log(f"[CTRL+T-MULTI] filename edit found by GetDlgItem {name} hwnd={item}")
                    return item
                for child in _iter_child_windows(item, recursive=True):
                    try:
                        if str(get_class_name(child) or "") == "Edit":
                            log(
                                f"[CTRL+T-MULTI] filename edit found under GetDlgItem {name} "
                                f"item={item} item_cls={item_cls!r} edit={child}"
                            )
                            return int(child)
                    except Exception:
                        continue
                log(f"[CTRL+T-MULTI] GetDlgItem {name} hwnd={item} cls={item_cls!r} has no Edit child")
        except Exception as e:
            log(f"[CTRL+T-MULTI] GetDlgItem {name} lookup fail err={e}")

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
            if ctrl_id == CMB13:
                score += 9000000
            if parent_id == EDT1:
                score += 5000000
            if parent_id == CMB13:
                score += 4500000
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


def _find_filename_edit_hwnd_retry(
    dialog_hwnd: int,
    *,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    timeout_sec: float = 1.5,
) -> int:
    deadline = time.perf_counter() + max(0.2, float(timeout_sec))
    attempt = 0
    while time.perf_counter() < deadline:
        attempt += 1
        hwnd = _find_filename_edit_hwnd(dialog_hwnd, log=log)
        if hwnd:
            if attempt > 1:
                log(f"[CTRL+T-MULTI] filename edit found after retry attempt={attempt}")
            return hwnd
        sleep_abs(0.10)
    return 0


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


def _focus_filename_edit(
    *,
    dialog_hwnd: int,
    edit_hwnd: int,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> None:
    try:
        user32.SetForegroundWindow(wintypes.HWND(int(dialog_hwnd or 0)))
    except Exception as e:
        log(f"[CTRL+T-MULTI] SetForegroundWindow dialog fail err={e}")
    try:
        user32.SetFocus(wintypes.HWND(int(edit_hwnd or 0)))
    except Exception as e:
        log(f"[CTRL+T-MULTI] SetFocus edit fail err={e}")
    try:
        user32.SendMessageW(wintypes.HWND(int(edit_hwnd or 0)), EM_SETSEL, 0, -1)
    except Exception as e:
        log(f"[CTRL+T-MULTI] EM_SETSEL edit fail err={e}")
    sleep_abs(0.06)


def _set_path_text_with_clipboard_then_fallback(
    *,
    dialog_hwnd: int,
    edit_hwnd: int,
    text: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    clipboard_settle_sec: float,
    after_paste_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    expected = _normalize_compare_text(text)

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_PATH_INPUT_ATTEMPT",
        ok=True,
        detail="focus filename edit and paste absolute path",
        extra={"expected_path": text, "dialog_hwnd": int(dialog_hwnd or 0), "edit_hwnd": int(edit_hwnd or 0)},
    )

    try:
        _focus_filename_edit(
            dialog_hwnd=dialog_hwnd,
            edit_hwnd=edit_hwnd,
            sleep_abs=sleep_abs,
            log=log,
        )
        try:
            send_keys_fast("^a")
            sleep_abs(0.03)
        except Exception as e:
            log(f"[CTRL+T-MULTI] Ctrl+A before paste fail err={e}")

        set_clipboard_text(str(text or ""))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=True,
            detail="path copied to clipboard",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        sleep_abs(max(0.03, float(clipboard_settle_sec)))

        send_keys_fast("^v")
        sleep_abs(max(0.08, float(after_paste_sec)))
        raw_actual = _get_edit_text_via_messages(edit_hwnd)
        if _normalize_compare_text(raw_actual) == expected:
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_PASTE",
                ok=True,
                detail="path paste verified",
                extra={"expected_path": text, "actual_text_length": len(raw_actual)},
            )
            log("[CTRL+T-MULTI] filename text verified after clipboard paste")
            return True

        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_PASTE",
            ok=False,
            detail="clipboard paste did not populate filename edit",
            extra={"expected_path": text, "actual": raw_actual, "actual_text_length": len(raw_actual)},
        )
        log(f"[CTRL+T-MULTI] clipboard paste verify fail expected={text!r} actual={raw_actual!r}")
    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=False,
            detail=str(e) or "clipboard paste failed",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        log(f"[CTRL+T-MULTI] clipboard path input fail err={e}")

    ok = _set_edit_text_verified(
        edit_hwnd,
        text,
        sleep_abs=sleep_abs,
        log=log,
        timeout_sec=max(1.2, float(after_paste_sec) + 1.2),
    )
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_DIRECT_SET",
        ok=ok,
        detail="fallback WM_SETTEXT filename edit",
        extra={"expected_path": text, "edit_hwnd": int(edit_hwnd or 0)},
    )
    return bool(ok)


def _bring_dialog_foreground(dialog_hwnd: int, *, sleep_abs: Callable[[float], None], log: Callable[[str], None]) -> None:
    h = int(dialog_hwnd or 0)
    if h <= 0:
        return
    try:
        user32.ShowWindow(wintypes.HWND(h), 9)
    except Exception as e:
        log(f"[CTRL+T-MULTI] ShowWindow dialog fail err={e}")
    try:
        user32.SetForegroundWindow(wintypes.HWND(h))
    except Exception as e:
        log(f"[CTRL+T-MULTI] SetForegroundWindow dialog fail err={e}")
    sleep_abs(0.08)


def _submit_path_text_by_dlgitem_fallback(
    *,
    dialog_hwnd: int,
    text: str,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    base_extra = {
        "expected_path": text,
        "dialog_hwnd": int(dialog_hwnd or 0),
        "method": "SetDlgItemTextW",
    }
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_DLGITEM_FALLBACK",
        ok=True,
        detail="try filename input using dialog item id",
        extra={**base_extra, "control_ids": [EDT1, CMB13]},
    )

    for ctrl_id, name in ((EDT1, "EDT1"), (CMB13, "CMB13")):
        extra = {**base_extra, "control_id": int(ctrl_id), "control_name": name}
        try:
            item = _safe_dialog_item(dialog_hwnd, ctrl_id)
            if item:
                extra["item_hwnd"] = item
                extra["item_class"] = str(get_class_name(item) or "")

            if not user32.SetDlgItemTextW(
                wintypes.HWND(int(dialog_hwnd or 0)),
                int(ctrl_id),
                ctypes.c_wchar_p(str(text or "")),
            ):
                _emit_debug_step(
                    debug_step,
                    "FILE_DIALOG_DLGITEM_FALLBACK",
                    ok=False,
                    detail=f"SetDlgItemTextW returned false for {name}",
                    extra=extra,
                )
                continue

            sleep_abs(0.12)
            verified = False
            if item:
                actual = _get_edit_text_via_messages(item)
                verified = _normalize_compare_text(actual) == _normalize_compare_text(text)
                extra["actual_text_length"] = len(actual)
                if not verified:
                    for child in _iter_child_windows(item, recursive=True):
                        try:
                            if str(get_class_name(child) or "") != "Edit":
                                continue
                            actual = _get_edit_text_via_messages(child)
                            verified = _normalize_compare_text(actual) == _normalize_compare_text(text)
                            extra["actual_text_length"] = len(actual)
                            extra["edit_hwnd"] = int(child)
                            if verified:
                                break
                        except Exception:
                            continue

            if not verified:
                _emit_debug_step(
                    debug_step,
                    "FILE_DIALOG_DLGITEM_FALLBACK",
                    ok=False,
                    detail=f"dialog item text was not verified for {name}",
                    extra=extra,
                )
                continue

            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_DLGITEM_FALLBACK",
                ok=True,
                detail=f"dialog item text verified for {name}",
                extra=extra,
            )
            user32.SendMessageW(wintypes.HWND(int(dialog_hwnd or 0)), WM_COMMAND, IDOK, 0)
            if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                log(f"[CTRL+T-MULTI] dialog closed after SetDlgItemTextW fallback {name}")
                return True
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_DLGITEM_FALLBACK",
                ok=False,
                detail=f"open dialog did not close after dialog item fallback {name}",
                extra=extra,
            )
        except Exception as e:
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_DLGITEM_FALLBACK",
                ok=False,
                detail=str(e) or f"dialog item fallback failed for {name}",
                extra=extra,
            )
            log(f"[CTRL+T-MULTI] dialog item fallback fail {name} err={e}")
            continue

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_DLGITEM_FALLBACK",
        ok=False,
        detail="open dialog did not close after dialog item fallback",
        extra=base_extra,
    )
    return False


def _submit_path_text_by_uia_fallback(
    *,
    dialog_hwnd: int,
    text: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    extra = {
        "expected_path": text,
        "dialog_hwnd": int(dialog_hwnd or 0),
        "method": "uia_focus_clipboard_enter",
    }
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_UIA_FALLBACK",
        ok=True,
        detail="try filename input using UI Automation",
        extra=extra,
    )

    try:
        _bring_dialog_foreground(dialog_hwnd, sleep_abs=sleep_abs, log=log)
        Desktop, _, _ = lazy_pywinauto()
        root = Desktop(backend="uia").window(handle=int(dialog_hwnd or 0))
        try:
            root.set_focus()
        except Exception:
            pass

        root_rect = root.rectangle()
        candidates: list[tuple[int, Any, dict[str, Any]]] = []
        for el in root.descendants():
            try:
                info = getattr(el, "element_info", None)
                ctrl_type = str(getattr(info, "control_type", "") or "")
                if ctrl_type not in {"Edit", "ComboBox"}:
                    continue
                rect = el.rectangle()
                w = max(0, int(rect.width()))
                h = max(0, int(rect.height()))
                if w <= 20 or h <= 8:
                    continue
                name = _safe_window_text(el)
                automation_id = str(getattr(info, "automation_id", "") or "")
                class_name = str(getattr(info, "class_name", "") or "")
                score = int(rect.bottom) * 10 + (w * h)
                lowered_name = name.casefold()
                if automation_id == str(EDT1):
                    score += 10_000_000
                if automation_id == str(CMB13):
                    score += 9_000_000
                if "file name" in lowered_name or "파일 이름" in name or "파일명" in name:
                    score += 5_000_000
                if int(rect.bottom) >= int(root_rect.bottom) - 160:
                    score += 1_000_000
                meta = {
                    "control_type": ctrl_type,
                    "automation_id": automation_id,
                    "class_name": class_name,
                    "name": name,
                    "rect": (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)),
                }
                candidates.append((score, el, meta))
            except Exception:
                continue

        if not candidates:
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_UIA_FALLBACK",
                ok=False,
                detail="no UIA filename input candidate",
                extra=extra,
            )
            return False

        candidates.sort(key=lambda x: x[0], reverse=True)
        score, el, meta = candidates[0]
        extra.update({"candidate_score": int(score), "candidate": meta, "candidate_count": len(candidates)})
        log(f"[CTRL+T-MULTI] UIA filename candidate score={score} meta={meta}")

        try:
            el.set_focus()
            sleep_abs(0.08)
        except Exception as e:
            log(f"[CTRL+T-MULTI] UIA candidate set_focus fail err={e}")

        set_clipboard_text(str(text or ""))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=True,
            detail="path copied to clipboard for UIA fallback",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        sleep_abs(0.08)
        send_keys_fast("^a")
        sleep_abs(0.04)
        send_keys_fast("^v")
        sleep_abs(0.15)
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_PASTE",
            ok=True,
            detail="path pasted by UIA fallback",
            extra=extra,
        )
        send_keys_fast("{ENTER}")
        if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_UIA_FALLBACK",
                ok=True,
                detail="open dialog closed after UIA fallback",
                extra=extra,
            )
            log("[CTRL+T-MULTI] dialog closed after UIA fallback")
            return True
    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_UIA_FALLBACK",
            ok=False,
            detail=str(e) or "UIA fallback failed",
            extra=extra,
        )
        log(f"[CTRL+T-MULTI] UIA fallback fail err={e}")
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_UIA_FALLBACK",
        ok=False,
        detail="open dialog did not close after UIA fallback",
        extra=extra,
    )
    return False


def _submit_path_text_by_initial_focus_fastpath(
    *,
    dialog_hwnd: int,
    text: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    extra = {
        "expected_path": text,
        "dialog_hwnd": int(dialog_hwnd or 0),
        "method": "current_focus_ctrl_a_clipboard_enter",
    }
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_INITIAL_FOCUS_INPUT",
        ok=True,
        detail="try filename input using the current focused field",
        extra=extra,
    )

    try:
        fg = int(get_foreground_hwnd() or 0)
        fg_root = _root_hwnd(fg)
        extra["foreground_hwnd_before"] = fg
        extra["foreground_root_before"] = fg_root
        if int(dialog_hwnd or 0) > 0 and fg_root != int(dialog_hwnd or 0):
            user32.SetForegroundWindow(wintypes.HWND(int(dialog_hwnd or 0)))
            extra["foreground_recovered"] = True
            sleep_abs(0.05)

        set_clipboard_text(str(text or ""))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=True,
            detail="path copied to clipboard for initial focus input",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        sleep_abs(0.05)
        send_keys_fast("^a")
        sleep_abs(0.03)
        send_keys_fast("^v")
        sleep_abs(0.10)
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_PASTE",
            ok=True,
            detail="path pasted by initial focused field",
            extra=extra,
        )
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_ENTER",
            ok=True,
            detail="submit open dialog by initial focused field",
            extra=extra,
        )
        send_keys_fast("{ENTER}")

        if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_INITIAL_FOCUS_INPUT",
                ok=True,
                detail="open dialog closed after initial focus input",
                extra=extra,
            )
            log("[CTRL+T-MULTI] dialog closed after initial focus input")
            return True
    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_INITIAL_FOCUS_INPUT",
            ok=False,
            detail=str(e) or "initial focus input failed",
            extra=extra,
        )
        log(f"[CTRL+T-MULTI] initial focus input fail err={e}")
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_INITIAL_FOCUS_INPUT",
        ok=False,
        detail="open dialog did not close after initial focus input",
        extra=extra,
    )
    return False


def _submit_path_text_by_keyboard_fallback(
    *,
    dialog_hwnd: int,
    text: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    extra = {
        "expected_path": text,
        "dialog_hwnd": int(dialog_hwnd or 0),
        "method": "alt_n_clipboard_enter",
    }
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_KEYBOARD_FALLBACK",
        ok=True,
        detail="try filename input using keyboard accelerator",
        extra=extra,
    )

    try:
        user32.SetForegroundWindow(wintypes.HWND(int(dialog_hwnd or 0)))
        sleep_abs(0.10)
    except Exception as e:
        log(f"[CTRL+T-MULTI] keyboard fallback SetForegroundWindow fail err={e}")

    try:
        set_clipboard_text(str(text or ""))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=True,
            detail="path copied to clipboard for keyboard fallback",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        sleep_abs(0.08)

        # Korean and English Windows common file dialogs use Alt+N for the
        # filename field ("파일 이름(N)" / "File name(N)").
        send_keys_fast("%n")
        sleep_abs(0.10)
        send_keys_fast("^a")
        sleep_abs(0.04)
        send_keys_fast("^v")
        sleep_abs(0.15)
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_PASTE",
            ok=True,
            detail="path pasted by keyboard fallback",
            extra={"expected_path": text},
        )
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_ENTER",
            ok=True,
            detail="submit open dialog by keyboard fallback",
            extra=extra,
        )
        send_keys_fast("{ENTER}")

        if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_KEYBOARD_FALLBACK",
                ok=True,
                detail="open dialog closed after keyboard fallback",
                extra=extra,
            )
            log("[CTRL+T-MULTI] dialog closed after keyboard fallback")
            return True
    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_KEYBOARD_FALLBACK",
            ok=False,
            detail=str(e) or "keyboard fallback failed",
            extra=extra,
        )
        log(f"[CTRL+T-MULTI] keyboard fallback fail err={e}")
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_KEYBOARD_FALLBACK",
        ok=False,
        detail="open dialog did not close after keyboard fallback",
        extra=extra,
    )
    return False


def _submit_path_text_by_geometry_fallback(
    *,
    dialog_hwnd: int,
    text: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    try:
        l, t, r, b = get_window_rect(dialog_hwnd)
    except Exception:
        l = t = r = b = 0
    w = max(0, int(r - l))
    h = max(0, int(b - t))
    x = int(l + (w * 0.45))
    y_candidates = [
        int(b - max(62, min(92, h * 0.105))),
        int(b - max(78, min(116, h * 0.135))),
    ]
    extra = {
        "expected_path": text,
        "dialog_hwnd": int(dialog_hwnd or 0),
        "method": "bottom_filename_click_clipboard_enter",
        "dialog_rect": (int(l), int(t), int(r), int(b)),
        "x": x,
        "y_candidates": y_candidates,
    }
    if w <= 200 or h <= 180:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_GEOMETRY_FALLBACK",
            ok=False,
            detail="dialog rect too small for geometry fallback",
            extra=extra,
        )
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_GEOMETRY_FALLBACK",
        ok=True,
        detail="try filename input using bottom field click",
        extra=extra,
    )

    try:
        _bring_dialog_foreground(dialog_hwnd, sleep_abs=sleep_abs, log=log)
        set_clipboard_text(str(text or ""))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLIPBOARD_SET",
            ok=True,
            detail="path copied to clipboard for geometry fallback",
            extra={"expected_path": text, "clipboard_text_length": len(str(text or ""))},
        )
        sleep_abs(0.08)

        _, _, click = lazy_pywinauto()
        for y in y_candidates:
            _bring_dialog_foreground(dialog_hwnd, sleep_abs=sleep_abs, log=log)
            click(coords=(x, int(y)))
            sleep_abs(0.08)
            send_keys_fast("^a")
            sleep_abs(0.04)
            send_keys_fast("^v")
            sleep_abs(0.15)
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_PASTE",
                ok=True,
                detail="path pasted by geometry fallback",
                extra={**extra, "clicked": (x, int(y))},
            )
            send_keys_fast("{ENTER}")
            if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                _emit_debug_step(
                    debug_step,
                    "FILE_DIALOG_GEOMETRY_FALLBACK",
                    ok=True,
                    detail="open dialog closed after geometry fallback",
                    extra={**extra, "clicked": (x, int(y))},
                )
                log(f"[CTRL+T-MULTI] dialog closed after geometry fallback x={x} y={y}")
                return True
            sleep_abs(0.15)
    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_GEOMETRY_FALLBACK",
            ok=False,
            detail=str(e) or "geometry fallback failed",
            extra=extra,
        )
        log(f"[CTRL+T-MULTI] geometry fallback fail err={e}")
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_GEOMETRY_FALLBACK",
        ok=False,
        detail="open dialog did not close after geometry fallback",
        extra=extra,
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


def _navigate_open_dialog_to_folder(
    *,
    dialog_hwnd: int,
    folder_path: str,
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    debug_step: Optional[DebugStep],
) -> bool:
    folder = str(folder_path or "").strip()
    extra = {
        "dialog_hwnd": int(dialog_hwnd or 0),
        "target_folder": folder,
        "method": "ctrl_l_clipboard_enter",
    }
    if not folder or not os.path.isdir(folder):
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_NAVIGATE_FOLDER",
            ok=False,
            detail="target folder does not exist",
            extra={**extra, "exists": False},
        )
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_NAVIGATE_FOLDER",
        ok=True,
        detail="navigate open dialog to attachment folder",
        extra={**extra, "exists": True},
    )

    try:
        if int(dialog_hwnd or 0) > 0:
            user32.SetForegroundWindow(wintypes.HWND(int(dialog_hwnd or 0)))
            sleep_abs(0.08)
        set_clipboard_text(folder)
        sleep_abs(0.05)
        send_keys_fast("^l")
        sleep_abs(0.08)
        send_keys_fast("^a")
        sleep_abs(0.03)
        send_keys_fast("^v")
        sleep_abs(0.08)
        send_keys_fast("{ENTER}")
        sleep_abs(0.35)
        try:
            send_keys_fast("{F5}")
            sleep_abs(0.25)
        except Exception as refresh_error:
            log(f"[CTRL+T-MULTI] folder refresh after navigation failed err={refresh_error}")
            sleep_abs(0.20)
        ok = bool(user32.IsWindow(wintypes.HWND(int(dialog_hwnd or 0))))
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_NAVIGATE_FOLDER_DONE",
            ok=ok,
            detail="open dialog folder navigation completed" if ok else "open dialog closed during folder navigation",
            extra=extra,
        )
        return ok
    except Exception as e:
        log(f"[CTRL+T-MULTI] folder navigation failed folder={folder!r} err={e}")
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_NAVIGATE_FOLDER_DONE",
            ok=False,
            detail=str(e) or "folder navigation failed",
            extra=extra,
        )
        return False


def _click_file_dialog_item(
    item: Any,
    *,
    add_to_selection: bool,
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
) -> bool:
    try:
        scroll_into_view = getattr(item, "scroll_into_view", None)
        if callable(scroll_into_view):
            scroll_into_view()
            sleep_abs(0.05)
    except Exception as e:
        log(f"[CTRL+T-MULTI] file item scroll_into_view failed err={e}")

    try:
        rect = item.rectangle()
        x = int((int(rect.left) + int(rect.right)) / 2)
        y = int((int(rect.top) + int(rect.bottom)) / 2)
    except Exception as e:
        log(f"[CTRL+T-MULTI] file item rectangle failed err={e}")
        return False

    try:
        _, _, click = lazy_pywinauto()
        if add_to_selection:
            send_keys_fast("{VK_CONTROL down}")
            sleep_abs(0.03)
        click(coords=(x, y))
        sleep_abs(0.08)
        return True
    except Exception as e:
        log(f"[CTRL+T-MULTI] file item coordinate click failed err={e}")
        return False
    finally:
        if add_to_selection:
            try:
                send_keys_fast("{VK_CONTROL up}")
                sleep_abs(0.03)
            except Exception:
                pass


def _select_file_items_and_submit_open_dialog(
    *,
    dialog_hwnd: int,
    filenames: Sequence[str],
    send_keys_fast: Callable[[str], None],
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    submit_timeout_sec: float,
    debug_step: Optional[DebugStep],
) -> bool:
    targets = [os.path.basename(str(name or "").strip()) for name in (filenames or []) if str(name or "").strip()]
    targets = [name for name in targets if name]
    extra: dict[str, Any] = {
        "dialog_hwnd": int(dialog_hwnd or 0),
        "target_filenames": targets,
        "target_count": len(targets),
        "method": "uia_list_item_ctrl_click",
    }
    if not targets:
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_LIST_SELECT_ATTEMPT",
        ok=True,
        detail="select files from current folder list before opening",
        extra=extra,
    )

    try:
        if int(dialog_hwnd or 0) > 0:
            user32.SetForegroundWindow(wintypes.HWND(int(dialog_hwnd or 0)))
            sleep_abs(0.08)

        Desktop, _, _ = lazy_pywinauto()
        dialog = Desktop(backend="uia").window(handle=int(dialog_hwnd or 0))
        try:
            dialog.set_focus()
        except Exception:
            pass

        items = list(dialog.descendants(control_type="ListItem"))
        item_names = [_safe_window_text(item) for item in items]
        extra.update({"visible_item_count": len(items), "visible_item_names": item_names[:40]})

        matched: list[tuple[str, Any, str]] = []
        used_handles: set[int] = set()
        missing: list[str] = []
        for target in targets:
            found_item = None
            found_name = ""
            for item, item_name in zip(items, item_names):
                item_hwnd = _safe_element_hwnd(item)
                if item_hwnd and item_hwnd in used_handles:
                    continue
                if _file_dialog_item_matches(item_name, target):
                    found_item = item
                    found_name = item_name
                    if item_hwnd:
                        used_handles.add(item_hwnd)
                    break
            if found_item is None:
                missing.append(target)
                continue
            matched.append((target, found_item, found_name))

        if missing:
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_LIST_SELECT_FOUND",
                ok=False,
                detail="some target files were not visible in the file list",
                extra={**extra, "matched_count": len(matched), "missing_filenames": missing},
            )
            return False

        for idx, (target, item, item_name) in enumerate(matched):
            clicked = False
            try:
                if idx == 0:
                    select = getattr(item, "select", None)
                    if callable(select):
                        select()
                        sleep_abs(0.08)
                        clicked = True
                else:
                    iface = getattr(item, "iface_selection_item", None)
                    add_to_selection = getattr(iface, "AddToSelection", None)
                    if callable(add_to_selection):
                        add_to_selection()
                        sleep_abs(0.08)
                        clicked = True
            except Exception as e:
                log(f"[CTRL+T-MULTI] UIA selection pattern failed target={target!r} err={e}")

            if not clicked:
                clicked = _click_file_dialog_item(
                    item,
                    add_to_selection=idx > 0,
                    send_keys_fast=send_keys_fast,
                    sleep_abs=sleep_abs,
                    log=log,
                )

            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_LIST_SELECT_ITEM",
                ok=bool(clicked),
                detail="selected file list item" if clicked else "failed to select file list item",
                extra={"target_filename": target, "item_text": item_name, "index": idx},
            )
            if not clicked:
                return False

        btn_hwnd = _find_open_button_hwnd(dialog_hwnd, log=log)
        if btn_hwnd:
            try:
                user32.SendMessageW(wintypes.HWND(btn_hwnd), BM_CLICK, 0, 0)
                if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                    _emit_debug_step(
                        debug_step,
                        "FILE_DIALOG_LIST_SELECT_SUBMIT",
                        ok=True,
                        detail="open dialog closed after list item selection",
                        extra={**extra, "matched_count": len(matched), "submit_method": "bm_click"},
                    )
                    return True
            except Exception as e:
                log(f"[CTRL+T-MULTI] open button BM_CLICK after list select failed err={e}")

        try:
            send_keys_fast("{ENTER}")
            if _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=submit_timeout_sec):
                _emit_debug_step(
                    debug_step,
                    "FILE_DIALOG_LIST_SELECT_SUBMIT",
                    ok=True,
                    detail="open dialog closed by ENTER after list item selection",
                    extra={**extra, "matched_count": len(matched), "submit_method": "enter"},
                )
                return True
        except Exception as e:
            log(f"[CTRL+T-MULTI] ENTER after list select failed err={e}")

    except Exception as e:
        log(f"[CTRL+T-MULTI] list item select submit failed err={e}")
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_LIST_SELECT_ATTEMPT",
            ok=False,
            detail=str(e) or "list item select failed",
            extra=extra,
        )
        return False

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_LIST_SELECT_SUBMIT",
        ok=False,
        detail="open dialog did not close after list item selection",
        extra=extra,
    )
    return False


def _cleanup_file_dialog_flow(
    *,
    prefer_hwnd: int,
    sleep_abs: Callable[[float], None],
    log: Callable[[str], None],
    debug_step: Optional[DebugStep],
    ok: bool,
    detail: str = "",
) -> None:
    _safe_cleanup_after_file_dialog(
        prefer_hwnd=int(prefer_hwnd or 0),
        sleep_abs=sleep_abs,
        log=log,
    )
    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_CLEANUP",
        ok=ok,
        detail=detail or "file dialog cleanup completed",
        extra={"prefer_hwnd": int(prefer_hwnd or 0)},
    )


def _send_paths_via_ctrl_t_dialog(
    *,
    file_paths: Sequence[str],
    send_keys_fast: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    ensure_foreground_chat: Callable[[], None],
    focus_chat_input_best_effort: Callable[[], bool],
    sleep_abs: Callable[[float], None],
    timeout_sec: float,
    log: Callable[[str], None],
    timings: Optional[Mapping[str, float]] = None,
    prefer_hwnd: int = 0,
    get_foreground_hwnd_cb: Optional[Callable[[], int]] = None,
    debug_step: Optional[DebugStep] = None,
    post_open_hook: Optional[Callable[..., bool]] = None,
    dialog_input_mode: str = "navigate_then_names",
) -> bool:
    valid_paths = [str(p).strip() for p in (file_paths or []) if str(p).strip()]
    if not valid_paths:
        return True

    for p in valid_paths:
        if not os.path.exists(p):
            _emit_debug_step(
                debug_step,
                "ATTACHMENT_PATH_VALIDATE",
                ok=False,
                detail="file does not exist",
                extra={"path": p, "exists": False},
            )
            log(f"[CTRL+T-MULTI] file not found: {p}")
            return False

    tm = dict(timings or {})

    def _t(key: str, default: float = 0.0) -> float:
        return float(tm.get(key, default))

    input_plan = _build_dialog_input_plan(valid_paths, input_mode=dialog_input_mode)
    names_text = input_plan["names_text"]
    full_paths_text = input_plan["full_paths_text"]
    dialog_input_text = input_plan["input_text"]
    dialog_input_mode = input_plan["input_mode"]
    shared_parent_dir = input_plan["shared_parent_dir"]
    requires_folder_navigation = bool(input_plan.get("requires_folder_navigation"))
    if not full_paths_text:
        return False

    log(f"[CTRL+T-MULTI] names_text={names_text}")
    log(f"[CTRL+T-MULTI] full_paths_text={full_paths_text}")
    log(f"[CTRL+T-MULTI] dialog_input_mode={dialog_input_mode} input_text={dialog_input_text}")

    def _dialog_input_extra() -> dict[str, Any]:
        return {
            "expected_path": dialog_input_text,
            "dialog_input_text": dialog_input_text,
            "dialog_input_mode": dialog_input_mode,
            "requires_folder_navigation": bool(requires_folder_navigation),
            "full_paths_text": full_paths_text,
            "folder_and_names_text": input_plan.get("folder_and_names_text", ""),
            "names_text": names_text,
            "shared_parent_dir": shared_parent_dir,
            "file_count": len(valid_paths),
        }

    dialog_input_extra = _dialog_input_extra()

    _emit_debug_step(
        debug_step,
        "FILE_DIALOG_INPUT_STRATEGY",
        ok=True,
        detail=f"{dialog_input_mode} is used for file dialog input",
        extra=dialog_input_extra,
    )

    try:
        ensure_foreground_chat()
        focus_chat_input_best_effort()
        sleep_abs(0.02)
    except Exception as e:
        log(f"[CTRL+T-MULTI] pre-focus fail: {e}")

    try:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_OPEN_ATTEMPT",
            ok=True,
            detail="press Ctrl+T",
            extra={**dialog_input_extra, "prefer_hwnd": int(prefer_hwnd or 0)},
        )
        send_keys_fast("^t")
        t_wait0 = time.perf_counter()
        dialog_hwnd, dialog_meta = _wait_for_open_dialog(
            timeout_sec=max(2.5, _t("after_ctrl_t", 0.20) + 3.0),
            sleep_abs=sleep_abs,
            log=log,
            get_foreground_hwnd_cb=get_foreground_hwnd_cb,
        )
        elapsed_ms = int((time.perf_counter() - t_wait0) * 1000)
        if not dialog_hwnd:
            fg = int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0)
            extra = _window_extra(_root_hwnd(fg))
            extra.update(
                {
                    "timeout_ms": int(max(2.5, _t("after_ctrl_t", 0.20) + 3.0) * 1000),
                    "elapsed_ms": elapsed_ms,
                    "dialog_selection": dialog_meta,
                }
            )
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_WAIT_ACTIVE",
                ok=False,
                detail="open dialog was not detected",
                extra=extra,
            )
            _cleanup_file_dialog_flow(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
                ok=True,
                detail="cleanup after open dialog wait failure",
            )
            return False

        initial_settle = max(0.04, min(0.16, _t("initial_focus_settle", 0.08)))
        sleep_abs(initial_settle)
        extra = _window_extra(dialog_hwnd)
        extra.update(
            {
                "elapsed_ms": elapsed_ms,
                "settle_ms": int(initial_settle * 1000),
                "settle_kind": "initial_focus",
                "dialog_selection": dialog_meta,
            }
        )
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_WAIT_ACTIVE",
            ok=True,
            detail="open dialog is active",
            extra=extra,
        )

        submitted = False
        if dialog_input_mode == "navigate_then_names" and requires_folder_navigation:
            navigated = _navigate_open_dialog_to_folder(
                dialog_hwnd=dialog_hwnd,
                folder_path=shared_parent_dir,
                send_keys_fast=send_keys_fast,
                set_clipboard_text=set_clipboard_text,
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
            )
            if navigated:
                submitted = _select_file_items_and_submit_open_dialog(
                    dialog_hwnd=dialog_hwnd,
                    filenames=valid_paths,
                    send_keys_fast=send_keys_fast,
                    sleep_abs=sleep_abs,
                    log=log,
                    submit_timeout_sec=max(3.0, float(timeout_sec)),
                    debug_step=debug_step,
                )
                if not submitted:
                    dialog_input_mode = "absolute_paths"
                    dialog_input_text = full_paths_text
                    requires_folder_navigation = False
                    dialog_input_extra = _dialog_input_extra()
                    _emit_debug_step(
                        debug_step,
                        "FILE_DIALOG_INPUT_STRATEGY_FALLBACK",
                        ok=True,
                        detail="list item selection failed; fallback to absolute paths",
                        extra=dialog_input_extra,
                    )
            else:
                dialog_input_mode = "absolute_paths"
                dialog_input_text = full_paths_text
                requires_folder_navigation = False
                dialog_input_extra = _dialog_input_extra()
                _emit_debug_step(
                    debug_step,
                    "FILE_DIALOG_INPUT_STRATEGY_FALLBACK",
                    ok=True,
                    detail="folder navigation failed; fallback to absolute paths",
                    extra=dialog_input_extra,
                )

        if not requires_folder_navigation:
            submitted = _submit_path_text_by_initial_focus_fastpath(
                dialog_hwnd=dialog_hwnd,
                text=dialog_input_text,
                send_keys_fast=send_keys_fast,
                set_clipboard_text=set_clipboard_text,
                sleep_abs=sleep_abs,
                log=log,
                submit_timeout_sec=max(2.0, float(timeout_sec)),
                debug_step=debug_step,
            )

        submitted_via_warning = False
        if not submitted:
            warning_seen, warning_confirmed = _confirm_recoverable_multi_select_warning(
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
                expected_file_count=len(valid_paths),
                send_keys_fast=send_keys_fast,
                get_foreground_hwnd_cb=get_foreground_hwnd_cb,
                timeout_sec=0.8,
            )
            if warning_seen:
                if not warning_confirmed:
                    _cleanup_file_dialog_flow(
                        prefer_hwnd=int(prefer_hwnd or 0),
                        sleep_abs=sleep_abs,
                        log=log,
                        debug_step=debug_step,
                        ok=True,
                        detail="cleanup after recoverable warning confirm failure",
                    )
                    return False
                submitted = True
                submitted_via_warning = True

        if not submitted:
            settle = max(0.05, min(0.70, _t("focus_settle", 0.35)) - initial_settle)
            sleep_abs(settle)

            edit_hwnd = _find_filename_edit_hwnd_retry(
                dialog_hwnd,
                sleep_abs=sleep_abs,
                log=log,
                timeout_sec=1.5,
            )
            if edit_hwnd:
                if _set_path_text_with_clipboard_then_fallback(
                    dialog_hwnd=dialog_hwnd,
                    edit_hwnd=edit_hwnd,
                    text=dialog_input_text,
                    send_keys_fast=send_keys_fast,
                    set_clipboard_text=set_clipboard_text,
                    sleep_abs=sleep_abs,
                    log=log,
                    clipboard_settle_sec=_t("clipboard_settle", 0.05),
                    after_paste_sec=_t("after_paste_path", 0.10),
                    debug_step=debug_step,
                ):
                    _emit_debug_step(
                        debug_step,
                        "FILE_DIALOG_ENTER",
                        ok=True,
                        detail="submit open dialog",
                        extra={**dialog_input_extra, "dialog_hwnd": int(dialog_hwnd or 0)},
                    )
                    submitted = _confirm_dialog_fields_and_submit(
                        dialog_hwnd=dialog_hwnd,
                        edit_hwnd=edit_hwnd,
                        expected_text=dialog_input_text,
                        sleep_abs=sleep_abs,
                        log=log,
                        submit_timeout_sec=max(3.0, float(timeout_sec)),
                    )
                else:
                    log("[CTRL+T-MULTI] filename edit path input failed; trying keyboard fallback")
            else:
                log("[CTRL+T-MULTI] filename edit not found after retry; trying keyboard fallback")

        if not submitted:
            submitted = _submit_path_text_by_dlgitem_fallback(
                dialog_hwnd=dialog_hwnd,
                text=dialog_input_text,
                sleep_abs=sleep_abs,
                log=log,
                submit_timeout_sec=max(3.0, float(timeout_sec)),
                debug_step=debug_step,
            )

        if not submitted:
            submitted = _submit_path_text_by_uia_fallback(
                dialog_hwnd=dialog_hwnd,
                text=dialog_input_text,
                send_keys_fast=send_keys_fast,
                set_clipboard_text=set_clipboard_text,
                sleep_abs=sleep_abs,
                log=log,
                submit_timeout_sec=max(3.0, float(timeout_sec)),
                debug_step=debug_step,
            )

        if not submitted:
            submitted = _submit_path_text_by_keyboard_fallback(
                dialog_hwnd=dialog_hwnd,
                text=dialog_input_text,
                send_keys_fast=send_keys_fast,
                set_clipboard_text=set_clipboard_text,
                sleep_abs=sleep_abs,
                log=log,
                submit_timeout_sec=max(3.0, float(timeout_sec)),
                debug_step=debug_step,
            )

        if not submitted:
            submitted = _submit_path_text_by_geometry_fallback(
                dialog_hwnd=dialog_hwnd,
                text=dialog_input_text,
                send_keys_fast=send_keys_fast,
                set_clipboard_text=set_clipboard_text,
                sleep_abs=sleep_abs,
                log=log,
                submit_timeout_sec=max(3.0, float(timeout_sec)),
                debug_step=debug_step,
            )

        if not submitted:
            warning_seen, warning_confirmed = _confirm_recoverable_multi_select_warning(
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
                expected_file_count=len(valid_paths),
                send_keys_fast=send_keys_fast,
                get_foreground_hwnd_cb=get_foreground_hwnd_cb,
                timeout_sec=0.8,
            )
            if warning_seen:
                if not warning_confirmed:
                    _cleanup_file_dialog_flow(
                        prefer_hwnd=int(prefer_hwnd or 0),
                        sleep_abs=sleep_abs,
                        log=log,
                        debug_step=debug_step,
                        ok=True,
                        detail="cleanup after recoverable warning confirm failure",
                    )
                    return False
                submitted = True
                submitted_via_warning = True

        if not submitted:
            extra = _window_extra(dialog_hwnd)
            extra.update({**dialog_input_extra, "dialog_hwnd": int(dialog_hwnd or 0)})
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_CLOSED_CHECK",
                ok=False,
                detail="open dialog still exists",
                extra=extra,
            )
            _emit_debug_step(
                debug_step,
                "FILE_DIALOG_PATH_INPUT_FAILED",
                ok=False,
                detail="filename path input failed by hwnd and keyboard fallback",
                extra=extra,
            )
            log("[CTRL+T-MULTI] path input fallback failed or dialog did not close")
            _cleanup_file_dialog_flow(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
                ok=True,
                detail="cleanup after path input fallback failure",
            )
            return False

        warning_seen, warning_confirmed = _confirm_recoverable_multi_select_warning(
            sleep_abs=sleep_abs,
            log=log,
            debug_step=debug_step,
            expected_file_count=len(valid_paths),
            send_keys_fast=send_keys_fast,
            get_foreground_hwnd_cb=get_foreground_hwnd_cb,
            timeout_sec=1.2,
        )
        if warning_seen:
            if not warning_confirmed:
                _cleanup_file_dialog_flow(
                    prefer_hwnd=int(prefer_hwnd or 0),
                    sleep_abs=sleep_abs,
                    log=log,
                    debug_step=debug_step,
                    ok=True,
                    detail="cleanup after recoverable warning confirm failure",
                )
                return False
            submitted_via_warning = True

        dialog_closed = not bool(user32.IsWindow(wintypes.HWND(int(dialog_hwnd or 0))))
        if not dialog_closed and not submitted_via_warning:
            dialog_closed = _wait_for_dialog_close(dialog_hwnd, sleep_abs=sleep_abs, timeout_sec=0.5)
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_CLOSED_CHECK",
            ok=bool(dialog_closed or submitted_via_warning),
            detail="open dialog submitted after recoverable warning" if submitted_via_warning else "open dialog closed",
            extra={
                "dialog_hwnd": int(dialog_hwnd or 0),
                **dialog_input_extra,
                "submitted_via_warning": bool(submitted_via_warning),
                "dialog_closed": bool(dialog_closed),
            },
        )
        sleep_abs(max(0.15, _t("after_enter_path", 0.25)))

        _emit_debug_step(
            debug_step,
            "KAKAO_UPLOAD_WAIT_START",
            ok=True,
            detail="wait for Kakao file-send surface",
            extra={"timeout_ms": int(max(2.0, float(timeout_sec)) * 1000), "prefer_hwnd": int(prefer_hwnd or 0)},
        )
        hook = post_open_hook or send_files_dialog_hook
        ok = hook(
            chat_hwnd=int(prefer_hwnd or 0),
            send_keys_fast=send_keys_fast,
            sleep_abs=sleep_abs,
            log=log,
            timeout_sec=max(2.0, float(timeout_sec)),
            expected_file_count=len(valid_paths),
            debug_step=debug_step,
        )
        if not ok:
            _emit_debug_step(
                debug_step,
                "KAKAO_UPLOAD_NOT_STARTED",
                ok=False,
                detail="Kakao file-send hook returned false",
                extra=_window_extra(_root_hwnd(int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0))),
            )
            _cleanup_file_dialog_flow(
                prefer_hwnd=int(prefer_hwnd or 0),
                sleep_abs=sleep_abs,
                log=log,
                debug_step=debug_step,
                ok=True,
                detail="cleanup after Kakao upload start failure",
            )
            return False

        _emit_debug_step(
            debug_step,
            "KAKAO_UPLOAD_STARTED",
            ok=True,
            detail="Kakao file-send hook completed",
            extra={"prefer_hwnd": int(prefer_hwnd or 0)},
        )
        _cleanup_file_dialog_flow(
            prefer_hwnd=int(prefer_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
            debug_step=debug_step,
            ok=True,
            detail="cleanup after successful file attach",
        )
        sleep_abs(0.12)
        return True

    except Exception as e:
        _emit_debug_step(
            debug_step,
            "FILE_DIALOG_UNKNOWN_STATE",
            ok=False,
            detail=str(e) or "file dialog exception",
            extra=_window_extra(_root_hwnd(int((get_foreground_hwnd_cb or get_foreground_hwnd)() or 0))),
        )
        log(f"[CTRL+T-MULTI] exception: {e}")
        _cleanup_file_dialog_flow(
            prefer_hwnd=int(prefer_hwnd or 0),
            sleep_abs=sleep_abs,
            log=log,
            debug_step=debug_step,
            ok=True,
            detail="cleanup after file dialog exception",
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
    debug_step: Optional[DebugStep] = None,
    dialog_input_mode: str = "absolute_paths",
) -> bool:
    """
    단일 파일 Ctrl+T.
    기존 검증된 흐름 유지.
    """
    if not png_bytes:
        return True

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

    def _single_image_post_open_hook(**_kwargs: Any) -> bool:
        return bool(
            send_image_dialog_hook(
                timeout_sec=timeout_sec,
                key_delay=key_delay,
                debug=debug,
                log=log,
                timings=dlg_timings,
                prefer_hwnd=int(prefer_hwnd or 0),
            )
        )

    return _send_paths_via_ctrl_t_dialog(
        file_paths=[str(tmp_path)],
        send_keys_fast=send_keys_fast,
        set_clipboard_text=set_clipboard_text,
        ensure_foreground_chat=ensure_foreground_chat,
        focus_chat_input_best_effort=focus_chat_input_best_effort,
        sleep_abs=sleep_abs,
        timeout_sec=timeout_sec,
        log=log,
        timings=timings,
        prefer_hwnd=int(prefer_hwnd or 0),
        get_foreground_hwnd_cb=get_foreground_hwnd,
        debug_step=debug_step,
        post_open_hook=_single_image_post_open_hook,
        dialog_input_mode=dialog_input_mode,
    )


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
    debug_step: Optional[DebugStep] = None,
    dialog_input_mode: str = "navigate_then_names",
) -> bool:
    return _send_paths_via_ctrl_t_dialog(
        file_paths=file_paths,
        send_keys_fast=send_keys_fast,
        set_clipboard_text=set_clipboard_text,
        ensure_foreground_chat=ensure_foreground_chat,
        focus_chat_input_best_effort=focus_chat_input_best_effort,
        sleep_abs=sleep_abs,
        timeout_sec=timeout_sec,
        log=log,
        timings=timings,
        prefer_hwnd=int(prefer_hwnd or 0),
        get_foreground_hwnd_cb=get_foreground_hwnd,
        debug_step=debug_step,
        dialog_input_mode=dialog_input_mode,
    )
