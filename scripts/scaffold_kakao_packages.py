"""One-off: copy integration sources into packages/ and rewrite imports."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "backend" / "integrations"

PKG_WIN32 = ROOT / "packages" / "kakao_win32" / "src" / "kakao_win32"
PKG_DRIVER = ROOT / "packages" / "kakao_pc_driver" / "src" / "kakao_pc_driver"

KAKAO_FILES = [
    "driver.py",
    "hooks.py",
    "dialog.py",
    "image_attach_cache.py",
    "image_attach_ctrl_t.py",
    "image_attach_ctrl_v.py",
]


def rewrite(text: str) -> str:
    text = text.replace("backend.integrations.windows.win32_core", "kakao_win32.win32_core")
    text = text.replace("backend.integrations.windows import win32_core", "kakao_win32 import win32_core")
    text = text.replace("backend.integrations.kakaotalk.", "kakao_pc_driver.")
    return text


def read_git_source(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    data = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
    return data.decode("utf-8")


def main() -> None:
    PKG_WIN32.mkdir(parents=True, exist_ok=True)
    PKG_DRIVER.mkdir(parents=True, exist_ok=True)

    w32_src = SRC / "windows" / "win32_core.py"
    w32_dst = PKG_WIN32 / "win32_core.py"
    w32_dst.write_text(rewrite(read_git_source(w32_src)), encoding="utf-8", newline="\n")

    for name in KAKAO_FILES:
        src = SRC / "kakaotalk" / name
        dst = PKG_DRIVER / name
        dst.write_text(rewrite(read_git_source(src)), encoding="utf-8", newline="\n")

    print("copied:", w32_dst, "and", len(KAKAO_FILES), "driver modules")


if __name__ == "__main__":
    main()
