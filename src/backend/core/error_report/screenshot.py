from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PIL import ImageGrab
except Exception:  # pragma: no cover
    ImageGrab = None


def capture_fullscreen_to(path: Path) -> Optional[Path]:
    """
    전체 화면 캡처.
    - 다중 모니터 포함 시도
    - 실패하면 None 반환
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if ImageGrab is None:
            return None

        img = ImageGrab.grab(all_screens=True)
        img.save(str(path), format="PNG")
        return path
    except Exception:
        return None