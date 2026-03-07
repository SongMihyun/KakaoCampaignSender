# FILE: scripts/git_editor_wrapper.py
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_effective_commit_message_text(text: str) -> bool:
    if not text:
        return False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        return True
    return False


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def fallback_editor() -> list[str]:
    env_editor = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "").strip()
    if env_editor:
        return [env_editor]

    if os.name == "nt":
        return ["notepad"]
    return ["vi"]


def main() -> int:
    # Git editor는 보통 마지막 인자로 편집 대상 파일을 넘긴다.
    if len(sys.argv) < 2:
        return 0

    target = Path(sys.argv[-1]).resolve()
    text = read_text(target)

    # helper가 이미 실제 메시지를 써놓은 경우 editor를 열지 않고 종료
    if is_effective_commit_message_text(text):
        return 0

    cmd = fallback_editor() + [str(target)]
    try:
        completed = subprocess.run(cmd, check=False)
        return int(completed.returncode)
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())