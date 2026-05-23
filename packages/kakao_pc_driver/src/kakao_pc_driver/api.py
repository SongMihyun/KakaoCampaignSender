from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from kakao_pc_driver.com import ensure_com_sta
from kakao_pc_driver.driver import KakaoPcDriver, KakaoTarget


@dataclass(slots=True)
class SendSelfResult:
    ok: bool
    reason: str = ""


def list_kakao_targets() -> List[KakaoTarget]:
    ensure_com_sta()
    return KakaoPcDriver.list_targets()


def send_self_message(
    message: str,
    *,
    my_name: str = "",
    speed_mode: str = "normal",
    hwnd: Optional[int] = None,
) -> SendSelfResult:
    """
    Send a text notification to the KakaoTalk self chat.

    If the self-chat shortcut cannot be opened directly, my_name is used as
    the search fallback. This is the light entry point intended for FaxSender.
    """
    ensure_com_sta()
    targets = KakaoPcDriver.list_targets()
    if not targets:
        return SendSelfResult(False, "kakao_window_not_found")

    handle = int(hwnd) if hwnd is not None else int(targets[0].handle)
    driver = KakaoPcDriver(handle, speed_mode=speed_mode)
    driver.start()
    try:
        driver.send_self_notification(message, my_name=my_name)
        return SendSelfResult(True)
    except Exception as e:
        return SendSelfResult(False, str(e))
    finally:
        driver.stop()


def send_to_contact(
    name: str,
    message: str,
    *,
    image_bytes_list: Optional[List[bytes]] = None,
    speed_mode: str = "normal",
    hwnd: Optional[int] = None,
) -> SendSelfResult:
    """Open a chat by contact name and send a text message plus optional images."""
    ensure_com_sta()
    targets = KakaoPcDriver.list_targets()
    if not targets:
        return SendSelfResult(False, "kakao_window_not_found")

    handle = int(hwnd) if hwnd is not None else int(targets[0].handle)
    driver = KakaoPcDriver(handle, speed_mode=speed_mode)
    driver.start()
    try:
        driver.send_to_name(name, message, image_bytes_list or [])
        return SendSelfResult(True)
    except Exception as e:
        return SendSelfResult(False, str(e))
    finally:
        driver.stop()
