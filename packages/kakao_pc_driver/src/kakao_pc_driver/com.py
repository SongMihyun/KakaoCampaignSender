from __future__ import annotations

import ctypes
from ctypes import wintypes

ole32 = ctypes.WinDLL("ole32", use_last_error=True)

COINIT_APARTMENTTHREADED = 0x2
S_OK = 0x00000000
S_FALSE = 0x00000001

HRESULT = getattr(wintypes, "HRESULT", ctypes.c_long)

ole32.CoInitializeEx.argtypes = [wintypes.LPVOID, wintypes.DWORD]
ole32.CoInitializeEx.restype = HRESULT
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None

_com_inited = False


def ensure_com_sta() -> bool:
    """Initialize COM as STA for the current thread when possible."""
    global _com_inited
    if _com_inited:
        return True
    hr = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
    if hr in (S_OK, S_FALSE):
        _com_inited = True
        return True
    return False


def uninitialize_com() -> None:
    global _com_inited
    if not _com_inited:
        return
    try:
        ole32.CoUninitialize()
    except Exception:
        pass
    _com_inited = False
