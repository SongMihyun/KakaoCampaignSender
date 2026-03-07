from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

def _install_dir() -> str:
    exe = getattr(sys, "executable", "")  # 설치형 exe 경로
    return os.path.dirname(exe) if exe else ""

def find_uninstaller() -> Optional[str]:
    """
    Inno Setup: 보통 unins000.exe
    NSIS: uninst.exe / uninstall.exe 등
    설치 폴더에서 흔한 파일명을 탐색.
    """
    d = _install_dir()
    if not d or not os.path.isdir(d):
        return None

    names = []
    try:
        names = os.listdir(d)
    except Exception:
        return None

    candidates = []
    for n in names:
        low = n.lower()
        if low.startswith("unins") and low.endswith(".exe"):
            candidates.append(os.path.join(d, n))
        elif low in ("uninstall.exe", "uninst.exe", "uninstaller.exe"):
            candidates.append(os.path.join(d, n))

    return candidates[0] if candidates else None

def launch_uninstaller(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    subprocess.Popen([path], shell=False)