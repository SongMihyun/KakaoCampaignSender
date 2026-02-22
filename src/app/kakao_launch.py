# src/app/kakao_launch.py
from __future__ import annotations

import os
import ctypes
from ctypes import wintypes
from typing import Optional, List


def try_find_kakao_exe() -> Optional[str]:
    """
    KakaoTalk.exe 자동 탐지:
    1) 레지스트리 App Paths
    2) Program Files 후보
    3) LocalAppData 후보
    """
    # 1) Registry App Paths
    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\KakaoTalk.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\KakaoTalk.exe",
        ]
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for k in keys:
                try:
                    with winreg.OpenKey(root, k) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.isfile(val):
                            return val
                except Exception:
                    continue
    except Exception:
        pass

    # 2) Common install paths
    candidates: List[str] = []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    la = os.environ.get("LOCALAPPDATA", "")

    candidates += [
        os.path.join(pf, "Kakao", "KakaoTalk", "KakaoTalk.exe"),
        os.path.join(pf86, "Kakao", "KakaoTalk", "KakaoTalk.exe"),
        os.path.join(pf, "KakaoTalk", "KakaoTalk.exe"),
        os.path.join(pf86, "KakaoTalk", "KakaoTalk.exe"),
    ]
    if la:
        candidates += [
            os.path.join(la, "Kakao", "KakaoTalk", "KakaoTalk.exe"),
            os.path.join(la, "Programs", "KakaoTalk", "KakaoTalk.exe"),
        ]

    for p in candidates:
        if p and os.path.isfile(p):
            return p

    return None


def shell_runas(exe_path: str, args: str = "", cwd: Optional[str] = None) -> None:
    """
    ShellExecuteW 'runas'로 관리자 실행
    """
    exe_path = os.path.abspath(exe_path)
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f"exe not found: {exe_path}")

    ShellExecuteW = ctypes.windll.shell32.ShellExecuteW
    ShellExecuteW.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int
    ]
    ShellExecuteW.restype = wintypes.HINSTANCE

    verb = "runas"
    params = args or ""
    directory = cwd or os.path.dirname(exe_path)
    show_cmd = 1  # SW_SHOWNORMAL

    r = ShellExecuteW(None, verb, exe_path, params, directory, show_cmd)
    if int(r) <= 32:
        raise RuntimeError(f"runas failed (code={int(r)})")
