
# ✅ FILE: src/app/sender/image_dib_cache.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Dict

from PIL import Image


@dataclass
class DibEntry:
    dib: bytes
    size: int


class PngToDibCache:
    """
    PNG bytes -> DIB bytes 메모리 캐시.
    - 전송 반복(동일 이미지)에서 PIL 변환 비용 제거
    """
    def __init__(self, max_items: int = 256) -> None:
        self._max = max(32, int(max_items))
        self._cache: Dict[str, DibEntry] = {}

    @staticmethod
    def _key(png_bytes: bytes) -> str:
        return hashlib.sha1(png_bytes).hexdigest()

    def get(self, png_bytes: bytes) -> bytes:
        if not png_bytes:
            return b""
        k = self._key(png_bytes)
        hit = self._cache.get(k)
        if hit and hit.size == len(png_bytes):
            return hit.dib

        with Image.open(BytesIO(png_bytes)) as img:
            img = img.convert("RGB")
            out = BytesIO()
            img.save(out, format="BMP")
            bmp = out.getvalue()

        dib = bmp[14:]  # BMP header 제거

        # simple prune
        if len(self._cache) >= self._max:
            self._cache.pop(next(iter(self._cache.keys())), None)

        self._cache[k] = DibEntry(dib=dib, size=len(png_bytes))
        return dib