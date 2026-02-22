
# ✅ FILE: src/app/sender/kakao_dialog_send.py
from __future__ import annotations

import logging
import time
from typing import List, Tuple

from app.sender.win32_core import (
    SW_RESTORE,
    get_foreground_hwnd,
    get_window_rect,
    get_window_text,
    is_window,
    lazy_pywinauto,
    user32,
)


def get_logger(name: str = "kakao_dialog_send", debug: bool = True) -> logging.Logger:
    logger = logging.getLogger(name)
    if debug:
        if not logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)
    return logger


def _looks_like_kakao_context(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    tl = t.lower()
    if ("카카오톡" in t) or ("kakaotalk" in tl):
        return True
    if ("사진" in t) or ("보내" in t) or ("전송" in t):
        return True
    return False


def _candidate_click_points(rect: Tuple[int, int, int, int]) -> List[Tuple[int, int]]:
    l, t, r, b = rect
    w = r - l
    h = b - t
    if w <= 0 or h <= 0:
        return []

    p1 = (int(l + w * 0.50), int(b - 60))
    p2 = (int(r - 90), int(b - 60))
    p3 = (int(l + w * 0.50), int(b - 95))
    p4 = (int(r - 90), int(b - 95))

    uniq: List[Tuple[int, int]] = []
    seen: set[Tuple[int, int]] = set()
    for p in (p1, p2, p3, p4):
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq


def _fallback_click_foreground_best_effort(*, logger: logging.Logger) -> bool:
    fg = get_foreground_hwnd()
    if not fg or not is_window(fg):
        return False

    title = get_window_text(fg)
    if not _looks_like_kakao_context(title):
        logger.info(f"[IMG-DLG] fg not kakao-like -> skip click. hwnd={fg} title='{title}'")
        return False

    rect = get_window_rect(fg)
    l, t, r, b = rect
    if (r - l) < 200 or (b - t) < 160:
        return False

    try:
        user32.ShowWindow(fg, SW_RESTORE)  # type: ignore[arg-type]
    except Exception:
        pass

    points = _candidate_click_points(rect)
    if not points:
        return False

    _, _, click = lazy_pywinauto()

    for (x, y) in points:
        logger.info(f"[IMG-DLG] click candidate hwnd={fg} title='{title}' click=({x},{y})")
        try:
            click(coords=(x, y))
            return True
        except Exception as e:
            logger.info(f"[IMG-DLG] click 실패 ({x},{y}): {e}")
            continue

    return False


def send_clipboard_image_dialog_force(
    *,
    timeout_sec: float = 1.2,
    key_delay: float = 0.02,
    debug: bool = True,
    enter_times: int = 2,
    enter_gap_sec: float = 0.04,
    try_interval: float = 0.12,
    loop_sleep: float = 0.02,
    post_click_sleep: float = 0.03,
    prefer_hwnd: int = 0,  # ✅ (호출부에서 이미 넘기고 있으면 매칭)
) -> bool:
    logger = get_logger(debug=debug)
    Desktop, send_keys, _ = lazy_pywinauto()

    t0 = time.time()
    timeout_sec = max(0.3, float(timeout_sec))

    last_try = 0.0
    enter_times = max(1, min(3, int(enter_times)))
    enter_gap_sec = max(0.02, float(enter_gap_sec))
    try_interval = max(0.03, float(try_interval))
    loop_sleep = max(0.005, float(loop_sleep))
    post_click_sleep = max(0.0, float(post_click_sleep))

    tries = 0
    clicks = 0
    enters = 0
    first_click_ms = -1

    logger.info(f"[IMG-DLG] wait start timeout={timeout_sec:.2f}s prefer_hwnd={prefer_hwnd}")

    while (time.time() - t0) < timeout_sec:
        now = time.time()

        if now - last_try > try_interval:
            last_try = now
            tries += 1

            clicked = _fallback_click_foreground_best_effort(logger=logger)
            if clicked:
                clicks += 1
                if first_click_ms < 0:
                    first_click_ms = int((time.time() - t0) * 1000)

                try:
                    time.sleep(post_click_sleep)
                    for i in range(enter_times):
                        send_keys("{ENTER}", pause=key_delay, with_spaces=True)
                        enters += 1
                        if i < enter_times - 1:
                            time.sleep(enter_gap_sec)
                except Exception:
                    pass

                total_ms = int((time.time() - t0) * 1000)
                logger.info(
                    f"[IMG-DLG] success total_ms={total_ms} tries={tries} clicks={clicks} enters={enters} first_click_ms={first_click_ms}"
                )
                return True

        time.sleep(loop_sleep)

    total_ms = int((time.time() - t0) * 1000)
    logger.info(
        f"[IMG-DLG] timeout total_ms={total_ms} tries={tries} clicks={clicks} enters={enters} first_click_ms={first_click_ms}"
    )
    return False

def _fallback_click_hwnd_best_effort(*, hwnd: int, logger: logging.Logger) -> bool:
    if not hwnd or not is_window(hwnd):
        return False

    title = get_window_text(hwnd)
    if not _looks_like_kakao_context(title):
        logger.info(f"[IMG-DLG] target hwnd not kakao-like -> skip. hwnd={hwnd} title='{title}'")
        return False

    rect = get_window_rect(hwnd)
    l, t, r, b = rect
    if (r - l) < 200 or (b - t) < 160:
        logger.info(f"[IMG-DLG] target rect too small -> skip. hwnd={hwnd} rect={rect} title='{title}'")
        return False

    try:
        user32.ShowWindow(hwnd, SW_RESTORE)  # type: ignore[arg-type]
    except Exception:
        pass

    points = _candidate_click_points(rect)
    if not points:
        return False

    _, _, click = lazy_pywinauto()

    for (x, y) in points:
        logger.info(f"[IMG-DLG] click target hwnd={hwnd} title='{title}' click=({x},{y})")
        try:
            click(coords=(x, y))
            return True
        except Exception as e:
            logger.info(f"[IMG-DLG] click 실패 ({x},{y}): {e}")
            continue

    return False