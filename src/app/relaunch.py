from __future__ import annotations

import sys
from pathlib import Path

from app.paths import project_root


def relaunch_executable_and_args() -> tuple[str, list[str], str]:
    """
    설정 가져오기/초기화 후 앱을 다시 띄울 때 사용할 실행 파일·인자·작업 디렉터리.
    - PyInstaller exe: exe만 실행, cwd=exe 폴더
    - 개발 실행: python.exe + main.py (+ 기존 argv), cwd=프로젝트 루트
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return str(exe), [], str(exe.parent)

    script = Path(sys.argv[0]).resolve()
    return sys.executable, [str(script), *sys.argv[1:]], str(project_root())
