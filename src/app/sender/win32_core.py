
# ✅ FILE: src/app/sender/win32_core.py
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Tuple, Optional

# -----------------------------------------------------------------------------
# Win32 core bindings + common helpers
# -----------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SW_RESTORE = 9

CF_UNICODETEXT = 13
CF_DIB = 8
GMEM_MOVEABLE = 0x0002

# --- prototypes ---
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL

user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

user32.SetActiveWindow.argtypes = [wintypes.HWND]
user32.SetActiveWindow.restype = wintypes.HWND

user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

# --- SendInput / SetCursorPos (fast click) ---
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

# UINT SendInput(UINT cInputs, LPINPUT pInputs, int cbSize);
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def lazy_pywinauto():
    from pywinauto import Desktop  # type: ignore
    from pywinauto.keyboard import send_keys  # type: ignore
    from pywinauto.mouse import click  # type: ignore
    return Desktop, send_keys, click


def _gle() -> int:
    try:
        return int(ctypes.get_last_error() or 0)
    except Exception:
        return 0


# -----------------------------------------------------------------------------
# Window helpers
# -----------------------------------------------------------------------------
def get_foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def is_window(hwnd: int) -> bool:
    try:
        return bool(hwnd and user32.IsWindow(wintypes.HWND(int(hwnd))))
    except Exception:
        return False


def get_window_text(hwnd: int) -> str:
    if not is_window(hwnd):
        return ""
    n = int(user32.GetWindowTextLengthW(wintypes.HWND(hwnd)) or 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buf, n + 1)
    return (buf.value or "").strip()


def get_window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    rc = wintypes.RECT()
    if not is_window(hwnd):
        return (0, 0, 0, 0)
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc)):
        return (0, 0, 0, 0)
    return (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))


def rect_center(rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
    l, t, r, b = rect
    return (int((l + r) / 2), int((t + b) / 2))


def get_pid(hwnd: int) -> int:
    try:
        if not is_window(hwnd):
            return 0
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(wintypes.HWND(int(hwnd)), ctypes.byref(pid))
        return int(pid.value or 0)
    except Exception:
        return 0


def foreground_hwnd_if_same_process(main_hwnd: int) -> int:
    fg = get_foreground_hwnd()
    if not fg or fg == int(main_hwnd):
        return 0
    if not is_window(fg):
        return 0
    main_pid = get_pid(int(main_hwnd))
    fg_pid = get_pid(int(fg))
    if main_pid and fg_pid and (main_pid == fg_pid):
        return int(fg)
    return 0


def is_kakaotalk_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    tl = t.lower()
    return ("카카오톡" in t) or ("kakaotalk" in tl)


def fallback_click_point(x: int, y: int) -> bool:
    try:
        _, _, click = lazy_pywinauto()
        click(coords=(int(x), int(y)))
        return True
    except Exception:
        return False


def sendinput_click(x: int, y: int) -> bool:
    """
    SendInput 기반 좌클릭.
    pywinauto click_input()이 간헐적으로 300~600ms 이상 늘어지는 케이스를 회피하기 위한 용도.
    """
    try:
        x = int(x)
        y = int(y)

        if not user32.SetCursorPos(x, y):
            return False

        INPUT_MOUSE = 0
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

        down = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0))
        up = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0))

        arr = (INPUT * 2)(down, up)
        sent = int(user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT)))
        return sent == 2
    except Exception:
        return False


def force_foreground_strict(hwnd: int, *, retries: int = 6, sleep: float = 0.06) -> None:
    """
    Foreground 강제 포커싱(Win32 + click fallback).
    """
    if not is_window(hwnd):
        raise RuntimeError("유효하지 않은 창 핸들입니다.")

    _, _, click = lazy_pywinauto()

    t_pid = wintypes.DWORD(0)
    t_tid = int(user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(t_pid)) or 0)
    cur_tid = int(kernel32.GetCurrentThreadId() or 0)

    for _ in range(max(1, int(retries))):
        try:
            user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
        except Exception:
            pass

        fg = user32.GetForegroundWindow()
        fg_pid = wintypes.DWORD(0)
        fg_tid = int(user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid)) or 0) if fg else 0

        attached_fg = False
        attached_t = False
        try:
            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
                attached_fg = True
            if t_tid and t_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, t_tid, True)
                attached_t = True

            try:
                user32.BringWindowToTop(wintypes.HWND(hwnd))
            except Exception:
                pass
            try:
                user32.SetActiveWindow(wintypes.HWND(hwnd))
            except Exception:
                pass
            try:
                user32.SetFocus(wintypes.HWND(hwnd))
            except Exception:
                pass

            user32.SetForegroundWindow(wintypes.HWND(hwnd))
        finally:
            if attached_t:
                user32.AttachThreadInput(cur_tid, t_tid, False)
            if attached_fg and fg_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, False)

        time.sleep(max(0.01, float(sleep)))
        if get_foreground_hwnd() == hwnd:
            return

        rect = get_window_rect(hwnd)
        if rect != (0, 0, 0, 0):
            x, y = rect_center(rect)
            try:
                click(coords=(x, y))
            except Exception:
                pass

        time.sleep(max(0.01, float(sleep)))
        if get_foreground_hwnd() == hwnd:
            return

    raise RuntimeError(
        f"포커스 실패(현재 foreground hwnd={get_foreground_hwnd()}). "
        f"※ 자동화 앱/대상앱 권한(관리자/일반)을 동일하게 맞추세요."
    )


# -----------------------------------------------------------------------------
# Clipboard helpers
# -----------------------------------------------------------------------------
def _open_clipboard_retry(*, retries: int = 10, interval_sec: float = 0.01) -> None:
    """
    OpenClipboard가 외부 점유로 실패하는 케이스가 잦아서 retry 제공.
    """
    for _ in range(max(1, int(retries))):
        if user32.OpenClipboard(None):
            return
        time.sleep(max(0.001, float(interval_sec)))
    raise RuntimeError(f"클립보드 열기 실패(OpenClipboard). gle={_gle()}")


def set_clipboard_text(text: str) -> None:
    text = (text or "")
    data = (text + "\0").encode("utf-16-le")

    _open_clipboard_retry(retries=10, interval_sec=0.01)
    try:
        user32.EmptyClipboard()

        hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not hmem:
            raise RuntimeError(f"GlobalAlloc 실패. gle={_gle()}")

        ptr = kernel32.GlobalLock(hmem)
        if not ptr:
            raise RuntimeError(f"GlobalLock 실패. gle={_gle()}")

        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(hmem)

        if not user32.SetClipboardData(CF_UNICODETEXT, hmem):
            raise RuntimeError(f"SetClipboardData 실패. gle={_gle()}")
    finally:
        user32.CloseClipboard()


def set_clipboard_dib(dib: bytes) -> None:
    dib = dib or b""

    _open_clipboard_retry(retries=10, interval_sec=0.01)
    try:
        user32.EmptyClipboard()

        hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
        if not hmem:
            raise RuntimeError(f"GlobalAlloc 실패. gle={_gle()}")

        ptr = kernel32.GlobalLock(hmem)
        if not ptr:
            raise RuntimeError(f"GlobalLock 실패. gle={_gle()}")

        ctypes.memmove(ptr, dib, len(dib))
        kernel32.GlobalUnlock(hmem)

        if not user32.SetClipboardData(CF_DIB, hmem):
            raise RuntimeError(f"SetClipboardData(CF_DIB) 실패. gle={_gle()}")
    finally:
        user32.CloseClipboard()


__all__ = [
    "user32",
    "kernel32",
    "SW_RESTORE",
    "CF_UNICODETEXT",
    "CF_DIB",
    "GMEM_MOVEABLE",
    "lazy_pywinauto",
    "get_foreground_hwnd",
    "is_window",
    "get_window_text",
    "get_window_rect",
    "rect_center",
    "get_pid",
    "foreground_hwnd_if_same_process",
    "is_kakaotalk_title",
    "fallback_click_point",
    "sendinput_click",
    "force_foreground_strict",
    "set_clipboard_text",
    "set_clipboard_dib",
]
