# app/platform/win_clipboard.py
from __future__ import annotations

import io
from typing import Optional

import win32clipboard
from PIL import Image


def set_clipboard_text(text: str) -> None:
    text = text or ""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_image_png_bytes(png_bytes: bytes) -> None:
    """
    PNG bytes -> DIB -> clipboard
    """
    if not png_bytes:
        raise ValueError("png_bytes is empty")

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    # BMP(DIB)로 변환: BMP 헤더(14바이트)는 제거해야 DIB가 됨
    output = io.BytesIO()
    img.save(output, "BMP")
    data = output.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()
