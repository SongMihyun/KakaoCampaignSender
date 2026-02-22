# src/app/platform/win_file_picker.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

try:
    from app.platform.win_file_picker_sta import (  # noqa: F401
        Filter,
        pick_open_file,
        pick_open_files,
        pick_save_file,
    )
except Exception as e:
    raise ImportError(
        "win_file_picker_sta.py 로드 실패.\n"
        "프로젝트 내 src/app/platform/win_file_picker_sta.py 가 존재하는지 확인하세요.\n"
        f"- 원인: {e}"
    ) from e
